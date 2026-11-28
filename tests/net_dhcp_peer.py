# SPDX-License-Identifier: Apache-2.0
"""Independent DHCP/ARP/UDP peer over QEMU's length-prefixed Ethernet socket.

This fixture constructs/parses wire packets itself and shares no DHCP parser or
lease state machine with the service under test. No host DHCP daemon is used.
"""
import hashlib
import secrets
import socket
import struct
import time
from net_tcp_window_peer import TcpWindowPeer, checksum, GUEST_MAC, HOST_MAC

IP1 = socket.inet_aton('10.0.2.15')
IP2 = socket.inet_aton('10.0.2.16')
SERVER1 = socket.inet_aton('10.0.2.2')
SERVER2 = socket.inet_aton('10.0.2.3')
BROADCAST = b'\xff' * 4


class DhcpPeer(TcpWindowPeer):
    def __init__(self):
        self.mode = None
        self.reports = []
        self.events = []
        super().__init__()

    def arm(self, mode):
        with self.lock:
            if self.error:
                raise AssertionError(self.error)
            self.mode = mode
            self.nonce = secrets.token_hex(16)
            self.report = {'scenario': mode, 'nonce': self.nonce, 'dhcp': [], 'arp_probes': [],
                           'declines': [], 'udp': [], 'dns_queries': 0, 'injected_malformed': 0}
            self.reports.append(self.report)
            self.address = IP1
            self.initial_xid = None
            self.renew_xid = None
            self.renew_time = None
            self.initial_request_time = None
            self.nak_sent = False
            self.conflict_sent = False
            self.malformed_sent = False
            return self.nonce

    def _ip_udp(self, source, destination, source_port, target_port, payload):
        udp = struct.pack('!HHHH', source_port, target_port, len(payload) + 8, 0) + payload
        pseudo = source + destination + struct.pack('!BBH', 0, 17, len(udp))
        udp = udp[:6] + struct.pack('!H', checksum(pseudo + udp) or 0xffff) + udp[8:]
        self.ip_id = (self.ip_id + 1) & 0xffff
        ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(udp), self.ip_id, 0, 64, 17, 0, source, destination)
        ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
        self._emit(0x0800, ip + udp)

    def _reply(self, request, message_type, issuer=SERVER1):
        data = bytearray(240)
        data[:3] = b'\x02\x01\x06'
        data[4:8] = request[4:8]
        if message_type != 6:
            data[16:20] = self.address
        data[28:34] = GUEST_MAC
        data[236:240] = b'\x63\x82\x53\x63'
        data += bytes([53, 1, message_type, 54, 4]) + issuer
        if message_type != 6:
            for code, value in ((1, b'\xff\xff\xff\0'), (3, SERVER1), (6, SERVER1),
                                (51, struct.pack('!I', 36)), (58, struct.pack('!I', 14)),
                                (59, struct.pack('!I', 24))):
                data += bytes([code, len(value)]) + value
        return bytes(data) + b'\xff'

    def _dhcp(self, data, destination):
        if len(data) < 241 or data[:3] != b'\x01\x01\x06' or data[28:34] != GUEST_MAC or data[236:240] != b'\x63\x82\x53\x63':
            raise ValueError('invalid guest BOOTP identity')
        options = {}
        offset = 240
        while offset < len(data):
            code = data[offset]; offset += 1
            if code == 255:
                break
            if not code:
                continue
            if offset == len(data) or offset + 1 + data[offset] > len(data) or code in options:
                raise ValueError('invalid/duplicate guest DHCP option')
            size = data[offset]; offset += 1
            options[code] = data[offset:offset + size]; offset += size
        message_type = options.get(53, b'\0')[0]
        xid = struct.unpack('!I', data[4:8])[0]
        record = {'type': message_type, 'xid': xid, 'ciaddr': socket.inet_ntoa(data[12:16]),
                  'destination': socket.inet_ntoa(destination), 'time': time.monotonic(),
                  'sha256': hashlib.sha256(data).hexdigest()}
        self.report['dhcp'].append(record)
        if message_type == 1:
            if self.mode == 'expire' and self.initial_xid is not None:
                return
            self._ip_udp(SERVER1, BROADCAST, 67, 68, self._reply(data, 2))
        elif message_type == 4:
            self.report['declines'].append(record)
        elif message_type == 3:
            if data[12:16] == b'\0' * 4:
                if self.mode == 'expire' and self.initial_xid is not None and xid != self.initial_xid:
                    return
                if self.initial_xid is None:
                    self.initial_xid = xid
                    self.initial_request_time = record['time']
                if self.mode == 'malformed' and not self.malformed_sent:
                    self.malformed_sent = True
                    valid = self._reply(data, 5)
                    duplicates = valid[:-1] + b'\x33\x04\0\0\0\x24\xff'
                    truncated = valid[:-1] + b'\x2b\x04\x01\xff'
                    foreign = self._reply(data, 5, socket.inet_aton('10.0.2.4'))
                    old = valid[:4] + struct.pack('!I', (xid ^ 0x42) or 1) + valid[8:]
                    for source, packet in ((SERVER1, duplicates), (SERVER1, truncated),
                                           (socket.inet_aton('10.0.2.4'), foreign), (SERVER1, old)):
                        self._ip_udp(source, BROADCAST, 67, 68, packet)
                        self.report['injected_malformed'] += 1
                self._ip_udp(SERVER1, BROADCAST, 67, 68, self._reply(data, 5))
            else:
                if xid == self.initial_xid:
                    raise ValueError('renewal reused original bound XID')
                if self.renew_xid is None:
                    self.renew_xid, self.renew_time = xid, record['time']
                if self.mode in ('expire', 'rebind_new_issuer') and xid != self.renew_xid:
                    raise ValueError('renew/rebind transaction changed XID')
                if self.mode == 'expire':
                    return
                if self.mode == 'nak_config_change' and not self.nak_sent:
                    self.nak_sent = True
                    self._ip_udp(SERVER1, BROADCAST, 67, 68, self._reply(data, 6))
                    self.address = IP2
                    return
                if self.mode == 'rebind_new_issuer':
                    if destination != BROADCAST:
                        return
                    self.report['rebind_same_xid'] = True
                    self.report['renew_to_rebind_seconds'] = record['time'] - self.renew_time
                    self._ip_udp(SERVER2, BROADCAST, 67, 68, self._reply(data, 5, SERVER2))
                else:
                    self._ip_udp(SERVER1, BROADCAST, 67, 68, self._reply(data, 5))
        else:
            raise ValueError('unexpected DHCP client message type: ' + str(message_type))

    def _receive(self, frame):
        with self.lock:
            if self.mode is None:
                # The raw NIC warmup precedes DHCP arming. It only needs an
                # ARP gateway reply; startup DISCOVERs intentionally get none.
                if len(frame) >= 42 and frame[12:14] == b'\x08\x06':
                    arp = frame[14:42]
                    if arp[:8] == bytes.fromhex('0001080006040001') and arp[24:28] == SERVER1:
                        self._emit(0x806, bytes.fromhex('0001080006040002') + HOST_MAC + SERVER1 + arp[8:18])
                return
            if len(frame) < 14:
                raise ValueError('truncated Ethernet')
            ether_type = struct.unpack('!H', frame[12:14])[0]
            if ether_type == 0x806:
                if len(frame) < 42:
                    raise ValueError('truncated ARP')
                arp = frame[14:42]
                if arp[:8] != bytes.fromhex('0001080006040001'):
                    return
                if arp[14:18] == b'\0' * 4 and arp[24:28] in (IP1, IP2):
                    self.report['arp_probes'].append(time.monotonic())
                    conflict = self.mode == 'acd_conflict' or (self.mode == 'conflict_backoff_recover' and not self.conflict_sent)
                    if conflict:
                        self.conflict_sent = True
                        self._emit(0x806, bytes.fromhex('0001080006040002') + HOST_MAC + arp[24:28] + GUEST_MAC + b'\0' * 4)
                elif arp[24:28] in (SERVER1, SERVER2):
                    self._emit(0x806, bytes.fromhex('0001080006040002') + HOST_MAC + arp[24:28] + arp[8:18])
                return
            if ether_type != 0x800:
                return
            ip = frame[14:]
            ihl = (ip[0] & 15) * 4 if ip else 0
            if len(ip) < 20 or ip[0] >> 4 != 4 or ihl < 20 or ihl > len(ip) or checksum(ip[:ihl]):
                raise ValueError('invalid guest IPv4')
            total = struct.unpack('!H', ip[2:4])[0]
            if not ihl <= total <= len(ip) or struct.unpack('!H', ip[6:8])[0] & 0x3fff:
                raise ValueError('invalid IPv4 length/fragment')
            if ip[9] != 17:
                raise ValueError('unadmitted application protocol')
            udp = ip[ihl:total]
            if len(udp) < 8:
                raise ValueError('truncated UDP')
            source, target, size, check = struct.unpack('!HHHH', udp[:8])
            if size != len(udp) or (check and checksum(ip[12:20] + struct.pack('!BBH', 0, 17, size) + udp)):
                raise ValueError('invalid guest UDP checksum/length')
            if (source, target) == (68, 67):
                self._dhcp(udp[8:], ip[16:20])
                return
            if ip[12:16] != self.address or ip[16:20] != SERVER1:
                raise ValueError('application used stale/unadmitted IPv4 tuple')
            if target == 53:
                self.report['dns_queries'] += 1
                return  # Deliberately pending until epoch retirement.
            if target != 3333 or udp[8:] != self.nonce.encode():
                raise ValueError('application did not send the fresh nonce on its sealed tuple')
            challenge = secrets.token_bytes(32)
            self.report['udp'].append({'source': socket.inet_ntoa(ip[12:16]), 'nonce': self.nonce,
                                       'challenge': challenge.hex(), 'payload_sha256': hashlib.sha256(udp[8:]).hexdigest()})
            self._ip_udp(SERVER1, self.address, 3333, source, challenge)

    def finish_scenario(self):
        with self.lock:
            if self.error:
                raise AssertionError(self.error)
            report = self.report
            if not report['arp_probes']:
                raise AssertionError('no real ACD probes')
            if self.mode == 'acd_conflict':
                if not report['declines'] or report['udp']:
                    raise AssertionError('conflict published traffic or omitted DECLINE')
            elif not report['udp']:
                raise AssertionError('no independent application challenge')
            if self.mode == 'conflict_backoff_recover':
                if not report['declines']:
                    raise AssertionError('no DECLINE before recovery')
                decline = report['declines'][0]['time']
                later = [event['time'] for event in report['dhcp'] if event['type'] == 1 and event['time'] > decline]
                if not later or min(later) - decline < 9:
                    raise AssertionError('conflict recovery skipped RFC backoff')
                report['backoff_seconds'] = min(later) - decline
            if self.mode == 'rebind_new_issuer' and not report.get('rebind_same_xid'):
                raise AssertionError('no same-XID broadcast rebind')
            report['status'] = 'passed'
            self.mode = None
            return report
