# SPDX-License-Identifier: Apache-2.0
"""Independent wire DHCP/DNS/TCP and real OpenSSL TLS peer for installed K4.

The guest runs its own VirtIO/lwIP/DHCP/TLS implementation. This endpoint parses
wire packets and uses Python's OpenSSL MemoryBIO; it shares no DHCP or TLS code
with the guest. Only disposable test certificates cross the two implementations.
"""
import copy
import hashlib
from pathlib import Path
import secrets
import socket
import ssl
import struct
import threading
import time

from net_dhcp_peer import DhcpPeer, SERVER1
from net_tcp_window_peer import checksum

sequence_mask = 0xffffffff


class installed_tls_peer(DhcpPeer):
    def __init__(self, certificates):
        self.certificates = Path(certificates)
        self.cases = []
        self.next_case = None
        self.ack_count = 0
        super().__init__()
        self.arm('renew')

    def begin_case(self, mode):
        with self.lock:
            if self.error:
                raise AssertionError(self.error)
            record = {'mode': mode, 'nonce': secrets.token_hex(16), 'flows': [],
                      'started': time.monotonic(), 'dhcp_ack_before': self.ack_count,
                      'dns_queries_before': sum(item['dns_queries'] for item in self.reports)}
            self.next_case = record
            self.cases.append(record)
            return record['nonce']

    def resume_leases(self):
        self.arm('renew')

    def _reply(self, request, message_type, issuer=SERVER1):
        data = bytearray(super()._reply(request, message_type, issuer))
        offset = 240
        while offset < len(data) and data[offset] != 255:
            code, size = data[offset:offset + 2]
            if code in (51, 58, 59):
                if size != 4:
                    raise AssertionError('fixture lease layout changed')
                struct.pack_into('!I', data, offset + 2, {51: 18, 58: 6, 59: 12}[code])
            offset += size + 2
        if message_type == 5:
            self.ack_count += 1
            self.report.setdefault('acks', []).append({'time': time.monotonic(),
                'number': self.ack_count, 'ciaddr': socket.inet_ntoa(request[12:16]),
                'lease_seconds': 18, 't1_seconds': 6, 't2_seconds': 12})
        return bytes(data)

    def _dhcp(self, data, destination):
        before = self.ack_count
        super()._dhcp(data, destination)
        if self.ack_count != before and data[12:16] != b'\0' * 4:
            for flow in self.flows.values():
                report = flow['report']
                if report.get('mode') == 'renew' and report.get('application_ready') and not report.get('renew_sent'):
                    flow['ssl'].write(('renew ' + report['nonce'] + '\n').encode())
                    report['renew_sent'] = time.monotonic()
                    report['renew_ack'] = self.ack_count
                    self._start_tls_close(flow)
                    self._flush(flow)

    def _emit_tcp(self, flow, flags=0x10, data=b'', sequence=None):
        options = b'\x02\x04\x05\xb4' if flags & 2 else b''
        head = struct.pack('!HHIIBBHHH', 443, flow['client_port'],
            flow['server_next'] if sequence is None else sequence, flow['client_next'],
            (20 + len(options)) // 4 << 4, flags, 65535, 0, 0) + options
        pseudo = SERVER1 + self.address + struct.pack('!BBH', 0, 6, len(head) + len(data))
        head = head[:16] + struct.pack('!H', checksum(pseudo + head + data)) + head[18:]
        self.ip_id = (self.ip_id + 1) & 0xffff
        ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(head) + len(data), self.ip_id,
                         0, 64, 6, 0, SERVER1, self.address)
        ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
        self._emit(0x800, ip + head + data)

    def _flush(self, flow):
        while flow['outgoing'].pending:
            payload = flow['outgoing'].read(1200)
            self._emit_tcp(flow, 0x18, payload)
            flow['server_next'] = (flow['server_next'] + len(payload)) & sequence_mask
            flow['report']['tls_sent_bytes'] += len(payload)

    def _start_tls_close(self, flow):
        flow['closing'] = True
        try:
            flow['ssl'].unwrap()
            flow['report']['peer_close_notify'] = True
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            pass
        flow['report']['server_close_notify'] = True

    def _advance_tls(self, flow):
        report = flow['report']
        try:
            if not report.get('tls_version'):
                flow['ssl'].do_handshake()
                report['tls_version'] = flow['ssl'].version()
                report['cipher'] = flow['ssl'].cipher()[0]
                if report['tls_version'] != 'TLSv1.3' or report.get('sni') != 'tls.xos.test':
                    raise ValueError('guest negotiated unexpected TLS identity/version')
            if flow['closing']:
                try:
                    flow['ssl'].unwrap()
                    report['peer_close_notify'] = True
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    pass
                return
            while True:
                data = flow['ssl'].read(4096)
                if not data:
                    raise ValueError('TLS close before the fresh application challenge')
                flow['request'].extend(data)
                if len(flow['request']) > 128:
                    raise ValueError('oversized application request')
                if b'\n' in flow['request']:
                    expected = (report['mode'] + ' ' + report['nonce'] + '\n').encode()
                    if bytes(flow['request']) != expected or report.get('application_ready'):
                        raise ValueError('application request differs from the fresh test nonce')
                    report['request_sha256'] = hashlib.sha256(expected).hexdigest()
                    report['application_ready'] = time.monotonic()
                    if report['mode'] == 'expire':
                        # GNU loading and TLS handshake may take time. Retire
                        # the lease only after a real verified application
                        # exchange exists, never infer it from host startup.
                        self.mode = 'expire'
                        self.renew_xid = None
                        self.renew_time = None
                        report['expiry_armed_after_tls_request'] = time.monotonic()
                        report['expiry_ack_count'] = self.ack_count
                    flow['ssl'].write(('ready ' + report['nonce'] + '\n').encode())
                    if report['mode'] in ('once', 'trust2'):
                        self._start_tls_close(flow)
                    return
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
            pass
        finally:
            self._flush(flow)

    def _tcp_packet(self, ip, ihl, total):
        tcp = ip[ihl:total]
        if len(tcp) < 20 or checksum(ip[12:20] + struct.pack('!BBH', 0, 6, len(tcp)) + tcp):
            raise ValueError('invalid guest TCP checksum/length')
        source, target, sequence, ack, offset, flags, window, _, urgent = struct.unpack('!HHIIBBHHH', tcp[:20])
        length = (offset >> 4) * 4
        if target != 443 or length < 20 or length > len(tcp) or urgent or ip[12:16] != self.address or ip[16:20] != SERVER1:
            raise ValueError('TCP escaped installed address/port tuple')
        payload = tcp[length:]
        flow = self.flows.get(source)
        if flags & 2:
            if flags != 2 or payload or self.next_case is None:
                raise ValueError('unexpected TCP SYN')
            if flow and flow['client_isn'] == sequence and not flow.get('closed'):
                self._emit_tcp(flow, 0x12, sequence=flow['server_isn'])
                return
            case = self.next_case
            report = {'mode': case['mode'], 'nonce': case['nonce'], 'client_port': source,
                      'server': '10.0.2.2:443', 'tls_sent_bytes': 0, 'tls_received_bytes': 0}
            case['flows'].append(report)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_3
            context.num_tickets = 0
            number = 2 if case['mode'] == 'trust2' else 1
            context.load_cert_chain(self.certificates / f'leaf-{number}.pem', self.certificates / f'leaf-{number}.key')
            context.set_servername_callback(lambda _ssl, name, _context: report.update(sni=name))
            incoming, outgoing = ssl.MemoryBIO(), ssl.MemoryBIO()
            isn = secrets.randbits(32)
            flow = {'report': report, 'done': threading.Event(), 'client_port': source,
                    'client_isn': sequence, 'client_next': (sequence + 1) & sequence_mask,
                    'server_isn': isn, 'server_next': (isn + 1) & sequence_mask,
                    'incoming': incoming, 'outgoing': outgoing, 'closing': False, 'request': bytearray(),
                    'ssl': context.wrap_bio(incoming, outgoing, server_side=True)}
            self.flows[source] = flow
            self._emit_tcp(flow, 0x12, sequence=isn)
            return
        if flow is None:
            return  # Late packets after service retirement do not authorize a flow.
        if flags & 4:
            flow['report']['tcp_reset'] = time.monotonic()
            flow['closed'] = True
            flow['done'].set()
            return
        if sequence != flow['client_next']:
            self._emit_tcp(flow)
            return  # Duplicate wire delivery; never feed a TLS record twice.
        if payload:
            flow['client_next'] = (flow['client_next'] + len(payload)) & sequence_mask
            flow['report']['tls_received_bytes'] += len(payload)
            self._emit_tcp(flow)
            flow['incoming'].write(payload)
            self._advance_tls(flow)
        if flags & 1:
            flow['client_next'] = (flow['client_next'] + 1) & sequence_mask
            self._emit_tcp(flow, 0x11)
            flow['server_next'] = (flow['server_next'] + 1) & sequence_mask
            flow['report']['tcp_fin'] = time.monotonic()
            flow['closed'] = True
            flow['done'].set()

    def _dns(self, ip, ihl, total):
        udp = ip[ihl:total]
        if len(udp) < 8:
            raise ValueError('short DNS UDP')
        source, target, size, check = struct.unpack('!HHHH', udp[:8])
        if target != 53:
            return False
        if (size != len(udp) or (check and checksum(ip[12:20] + struct.pack('!BBH', 0, 17, size) + udp))
                or ip[12:16] != self.address or ip[16:20] != SERVER1):
            raise ValueError('DNS used an invalid installed tuple')
        query = udp[8:]
        question = b'\x03tls\x03xos\x04test\0\0\x01\0\x01'
        if len(query) != 12 + len(question) or query[2:12] != b'\x01\0\0\x01\0\0\0\0\0\0' or query[12:] != question:
            raise ValueError('unexpected TLS DNS question')
        self.report['dns_queries'] += 1
        self.report['dns_answers'].append({'name': 'tls.xos.test', 'time': time.monotonic(),
                                          'source': socket.inet_ntoa(ip[12:16])})
        answer = query[:2] + struct.pack('!HHHHH', 0x8180, 1, 1, 0, 0) + question
        answer += struct.pack('!HHHIH4s', 0xc00c, 1, 1, 5, 4, SERVER1)
        self._ip_udp(SERVER1, self.address, 53, source, answer)
        return True

    def _receive(self, frame):
        if len(frame) >= 34 and frame[12:14] == b'\x08\0':
            ip = frame[14:]
            ihl = (ip[0] & 15) * 4
            total = struct.unpack('!H', ip[2:4])[0]
            if (ip[0] >> 4 != 4 or not 20 <= ihl <= total <= len(ip) or checksum(ip[:ihl])
                    or struct.unpack('!H', ip[6:8])[0] & 0x3fff):
                raise ValueError('invalid guest IPv4 frame')
            with self.lock:
                if ip[9] == 6:
                    self._tcp_packet(ip, ihl, total)
                    return
                if ip[9] == 17 and self._dns(ip, ihl, total):
                    return
        super()._receive(frame)

    def snapshot(self):
        with self.lock:
            if self.error:
                raise AssertionError(self.error)
            # The base peer records transport shutdown on live flow objects.
            # Freeze the verified snapshot before QEMU/peer teardown mutates
            # those objects, so normal teardown cannot rewrite prior evidence.
            return copy.deepcopy({'dhcp_epochs': self.reports, 'application_cases': self.cases,
                    'dhcp_ack_count': self.ack_count, 'tls_provider': ssl.OPENSSL_VERSION})
