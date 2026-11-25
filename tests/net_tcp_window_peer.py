# SPDX-License-Identifier: Apache-2.0
"""Private Ethernet peer for deterministic TCP close qualification.

QEMU's socket backend carries length-prefixed Ethernet frames over loopback TCP.
This peer owns the advertised TCP window, so host socket buffering cannot hide
whether the guest still has admitted, unsent bytes when it closes a connection.
The ordinary native UDP API supplies a close-completed barrier on the same NIC.
"""
import hashlib
import secrets
import socket
import struct
import threading

MASK = 0xffffffff
HOST_IP = socket.inet_aton('10.0.2.2')
GUEST_IP = socket.inet_aton('10.0.2.15')
HOST_MAC = bytes.fromhex('52550a000202')
GUEST_MAC = bytes.fromhex('525400123456')


def checksum(data):
    if len(data) & 1:
        data += b'\0'
    value = sum(struct.unpack('!' + 'H' * (len(data) // 2), data))
    while value >> 16:
        value = (value & 0xffff) + (value >> 16)
    return (~value) & 0xffff


class TcpWindowPeer:
    def __init__(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.flows = {}
        self.error = None
        self.connection = None
        self.ip_id = 0
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def begin(self, mode, nonce, challenge, shell):
        if mode not in ('queued', 'drained') or len(nonce) != 32 or len(challenge) != 32:
            raise ValueError('invalid close fixture inputs')
        with self.lock:
            if self.error:
                raise AssertionError(self.error)
            port = 41000 + 2 * len(self.flows)
            report = {'mode': mode, 'shell': shell, 'nonce': nonce, 'peer_port': port,
                      'challenge_sha256': hashlib.sha256(challenge).hexdigest(),
                      'zero_window_probe_frames': 0, 'fin_count': 0}
            flow = {'mode': mode, 'nonce': nonce.encode(), 'challenge': challenge,
                    'count': 4096 if mode == 'queued' else 8192,
                    'report': report, 'request': bytearray(), 'client_port': None,
                    'client_isn': None, 'server_isn': secrets.randbits(32),
                    'server_next': None, 'client_next': None, 'released': mode == 'drained',
                    'challenge_sent': False, 'drain_marker_sent': False, 'barrier_seen': False,
                    'fin_seen': False, 'done': threading.Event()}
            self.flows[port] = flow
            return port, report

    def finish(self, port, timeout=25):
        flow = self.flows[port]
        if not flow['done'].wait(timeout):
            raise AssertionError(self.error or f'TCP close peer did not finish: {flow["report"]}')
        if self.error:
            raise AssertionError(self.error)
        report = flow['report']
        if not flow['barrier_seen'] or not flow['fin_seen'] or len(flow['request']) != 32 + flow['count']:
            raise AssertionError('TCP close peer has incomplete evidence')
        report['queued_tx_bytes_verified'] = len(flow['request']) - 32
        report['request_sha256'] = hashlib.sha256(flow['request']).hexdigest()
        report['status'] = 'passed'

    def close(self):
        self.cancel.set()
        self.listener.close()
        if self.connection:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        self.worker.join(timeout=2)
        if self.worker.is_alive():
            raise AssertionError('packet peer failed to stop')

    def _read_exact(self, length):
        result = bytearray()
        while len(result) < length and not self.cancel.is_set():
            try:
                data = self.connection.recv(length - len(result))
            except socket.timeout:
                continue
            if not data:
                raise EOFError('QEMU packet connection closed')
            result.extend(data)
        return bytes(result)

    def _run(self):
        try:
            while not self.cancel.is_set():
                try:
                    self.connection, _ = self.listener.accept()
                    break
                except socket.timeout:
                    continue
            if self.cancel.is_set():
                return
            self.connection.settimeout(0.1)
            while not self.cancel.is_set():
                header = self._read_exact(4)
                if self.cancel.is_set():
                    return
                length = struct.unpack('!I', header)[0]
                if not 14 <= length <= 65536:
                    raise ValueError('invalid QEMU Ethernet frame length')
                frame = self._read_exact(length)
                if self.cancel.is_set():
                    return
                self._receive(frame)
        except Exception as error:
            if not self.cancel.is_set():
                self.error = str(error)
                with self.lock:
                    flows = list(self.flows.values())
                for flow in flows:
                    flow['report']['peer_error'] = self.error
                    flow['done'].set()

    def _emit(self, ether_type, payload):
        frame = (GUEST_MAC + HOST_MAC + struct.pack('!H', ether_type) + payload).ljust(60, b'\0')
        self.connection.sendall(struct.pack('!I', len(frame)) + frame)

    def _ip(self, protocol, payload):
        self.ip_id = (self.ip_id + 1) & 0xffff
        header = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(payload), self.ip_id, 0,
                             64, protocol, 0, HOST_IP, GUEST_IP)
        header = header[:10] + struct.pack('!H', checksum(header)) + header[12:]
        self._emit(0x0800, header + payload)

    def _tcp(self, port, flow, flags=0x10, payload=b'', *, sequence=None, syn=False):
        options = b'\x02\x04\x05\xb4' if syn else b''  # MSS 1460, no window scaling.
        # A tiny SYN window would also reduce lwIP's effective segment size
        # (snd_wnd_max / 2), testing segment-pool pressure instead of close.
        # The challenge shrinks this window to zero before the guest queues
        # any payload; receiving its first byte is the guest's synchronization.
        window = 0 if flow['challenge_sent'] and not flow['released'] else 65535
        header = struct.pack('!HHIIBBHHH', port, flow['client_port'],
                             flow['server_next'] if sequence is None else sequence,
                             flow['client_next'], (20 + len(options)) // 4 << 4, flags, window, 0, 0) + options
        pseudo = HOST_IP + GUEST_IP + struct.pack('!BBH', 0, 6, len(header) + len(payload))
        header = header[:16] + struct.pack('!H', checksum(pseudo + header + payload)) + header[18:]
        self._ip(6, header + payload)

    def _udp(self, port, target, payload):
        header = struct.pack('!HHHH', port, target, len(payload) + 8, 0)
        pseudo = HOST_IP + GUEST_IP + struct.pack('!BBH', 0, 17, len(header) + len(payload))
        header = header[:6] + struct.pack('!H', checksum(pseudo + header + payload) or 0xffff)
        self._ip(17, header + payload)

    def _receive(self, frame):
        ether_type = struct.unpack('!H', frame[12:14])[0]
        if ether_type == 0x0806:
            if len(frame) < 42:
                raise ValueError('truncated ARP')
            arp = frame[14:42]
            if arp[:8] == bytes.fromhex('0001080006040001') and arp[24:28] == HOST_IP:
                self._emit(0x0806, bytes.fromhex('0001080006040002') + HOST_MAC + HOST_IP + arp[8:18])
            return
        if ether_type != 0x0800:
            return  # NIC warmup includes non-IP traffic.
        ip = frame[14:]
        size = (ip[0] & 15) * 4 if ip else 0
        if len(ip) < 20 or ip[0] >> 4 != 4 or size < 20 or size > len(ip):
            raise ValueError('invalid IPv4 header')
        total = struct.unpack('!H', ip[2:4])[0]
        if not size <= total <= len(ip) or checksum(ip[:size]) or struct.unpack('!H', ip[6:8])[0] & 0x3fff:
            raise ValueError('invalid IPv4 length/checksum/fragment')
        if ip[12:16] != GUEST_IP or ip[16:20] != HOST_IP:
            raise ValueError('unexpected IPv4 address')
        payload = ip[size:total]
        pseudo = GUEST_IP + HOST_IP + struct.pack('!BBH', 0, ip[9], len(payload))
        if ip[9] == 6:
            self._receive_tcp(payload, pseudo)
        elif ip[9] == 17:
            self._receive_udp(payload, pseudo)

    def _receive_tcp(self, packet, pseudo):
        if len(packet) < 20 or checksum(pseudo + packet):
            raise ValueError('invalid TCP checksum/header')
        source, port, sequence, ack, offset, flags, _, _, _ = struct.unpack('!HHIIBBHHH', packet[:20])
        size = (offset >> 4) * 4
        if size < 20 or size > len(packet) or flags & 0x04:
            raise ValueError('invalid TCP header or unexpected RST')
        payload = packet[size:]
        with self.lock:
            flow = self.flows.get(port)
        if flow is None:
            raise ValueError('TCP connection without an armed fixture')
        if flags & 0x02:
            if flags != 0x02 or payload:
                raise ValueError('unexpected SYN shape')
            if flow['client_isn'] is not None and (flow['client_isn'] != sequence or flow['client_port'] != source):
                raise ValueError('replacement SYN in a live fixture')
            flow['client_port'], flow['client_isn'] = source, sequence
            flow['client_next'] = (sequence + 1) & MASK
            flow['server_next'] = (flow['server_isn'] + 1) & MASK
            flow['report']['client_initial_sequence'] = sequence
            flow['report']['peer_initial_sequence'] = flow['server_isn']
            self._tcp(port, flow, 0x12, sequence=flow['server_isn'], syn=True)
            return
        if source != flow['client_port'] or not flags & 0x10:
            raise ValueError('TCP tuple/ACK mismatch')
        if ((ack - (flow['server_isn'] + 1)) & MASK) > ((flow['server_next'] - (flow['server_isn'] + 1)) & MASK):
            raise ValueError('TCP ACK exceeds peer data')
        if payload:
            index = (sequence - (flow['client_isn'] + 1)) & MASK
            end = index + len(payload)
            expected = flow['nonce'] * (1 + flow['count'] // 32)
            if end > len(expected) or payload != expected[index:end]:
                raise ValueError('TCP request data mismatch')
            if flow['mode'] == 'queued' and flow['challenge_sent'] and not flow['released'] and end > 32:
                if index != 32 or len(payload) != 1 or flags & 0x01:
                    raise ValueError('TCP payload escaped the advertised zero window')
                flow['report']['zero_window_probe_frames'] += 1
                self._tcp(port, flow)
                return
            if index > len(flow['request']):
                raise ValueError('TCP request has a sequence gap')
            flow['request'].extend(payload[max(0, len(flow['request']) - index):])
            flow['client_next'] = (flow['client_isn'] + 1 + len(flow['request'])) & MASK
            if len(flow['request']) == 32 and not flow['challenge_sent']:
                flow['challenge_sent'] = True
                self._tcp(port, flow, 0x18, flow['challenge'])
                flow['server_next'] = (flow['server_next'] + 32) & MASK
            elif len(flow['request']) == 32 + flow['count'] and flow['mode'] == 'drained' and not flow['drain_marker_sent']:
                flow['drain_marker_sent'] = True
                self._tcp(port, flow, 0x18, b'\xa5')
                flow['server_next'] = (flow['server_next'] + 1) & MASK
            else:
                self._tcp(port, flow)
        if flags & 0x01:
            position = (sequence + len(payload)) & MASK
            if (not flow['released'] or len(flow['request']) != 32 + flow['count'] or
                    position != ((flow['client_isn'] + 1 + 32 + flow['count']) & MASK)):
                raise ValueError('FIN precedes the complete accepted payload')
            if not flow['fin_seen']:
                flow['fin_seen'] = True
                flow['report']['fin_count'] += 1
                flow['client_next'] = (position + 1) & MASK
                self._tcp(port, flow, 0x11)
                flow['server_next'] = (flow['server_next'] + 1) & MASK
            else:
                self._tcp(port, flow)
            if flow['barrier_seen']:
                flow['done'].set()

    def _receive_udp(self, packet, pseudo):
        if len(packet) < 8:
            raise ValueError('truncated UDP close barrier')
        source, port, length, check = struct.unpack('!HHHH', packet[:8])
        if length != len(packet) or (check and checksum(pseudo + packet)):
            raise ValueError('invalid UDP close barrier checksum/length')
        with self.lock:
            flow = self.flows.get(port - 1)
        if not flow or packet[8:] != flow['nonce'] or flow['barrier_seen']:
            raise ValueError('UDP close barrier identity mismatch')
        report = flow['report']
        if flow['mode'] == 'queued':
            if not flow['challenge_sent'] or flow['released'] or len(flow['request']) != 32 or flow['fin_seen']:
                raise ValueError('close barrier did not retain queued TCP bytes')
            report['close_barrier'] = {'advertised_window': 0, 'accepted_bytes': flow['count'],
                                       'queued_data_bytes_received': 0,
                                       'distinct_probe_bytes': int(bool(report['zero_window_probe_frames'])),
                                       'unsent_bytes_lower_bound': flow['count'] - int(bool(report['zero_window_probe_frames']))}
        else:
            if len(flow['request']) != 32 + flow['count'] or not flow['drain_marker_sent'] or not flow['fin_seen']:
                raise ValueError('drained close lacks the peer ACK/application barrier')
            report['close_barrier'] = {'advertised_window': 65535, 'accepted_bytes': 8192,
                                       'acknowledged_bytes_before_close': 8192}
        flow['barrier_seen'] = True
        report['close_barrier']['nonce_sha256'] = hashlib.sha256(packet[8:]).hexdigest()
        self._udp(port, source, packet[8:])
        if flow['mode'] == 'queued':
            flow['released'] = True
            self._tcp(port - 1, flow)
        if flow['fin_seen']:
            flow['done'].set()
