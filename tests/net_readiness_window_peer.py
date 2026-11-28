# SPDX-License-Identifier: Apache-2.0
"""Controlled handshake and TCP zero-window peer for actual libc poll calls."""
import struct
import threading

from net_tcp_window_peer import TcpWindowPeer, checksum


class readiness_window_peer(TcpWindowPeer):
    def __init__(self):
        self.protocol_lock = threading.RLock()
        super().__init__()

    def begin(self, nonce, challenge):
        port, report = super().begin('queued', nonce, challenge, 'glibc')
        flow = self.flows[port]
        flow.update(count=32768, syn_packet=None, handshake_released=False, pending_syn=threading.Event())
        report['purpose'] = 'nonblocking connect, arrival, consumed level, zero-window recovery'
        return port, report

    def _receive_tcp(self, packet, pseudo):
        with self.protocol_lock:
            self.receive_tcp_locked(packet, pseudo)

    def receive_tcp_locked(self, packet, pseudo):
        if len(packet) < 20 or checksum(pseudo + packet):
            raise ValueError('invalid readiness TCP envelope')
        port = struct.unpack('!H', packet[2:4])[0]
        flow = self.flows.get(port)
        if flow is not None and packet[13] & 2 and not flow['handshake_released']:
            if flow['syn_packet'] is not None and flow['syn_packet'] != (packet, pseudo):
                raise ValueError('pending connect changed SYN identity')
            flow['syn_packet'] = packet, pseudo
            flow['pending_syn'].set()
            return
        super()._receive_tcp(packet, pseudo)

    def release_handshake(self, port):
        if not self.flows[port]['pending_syn'].wait(5):
            raise AssertionError('pending connect emitted no SYN')
        with self.protocol_lock:
            flow = self.flows[port]
            if flow['syn_packet'] is None or flow['handshake_released']:
                raise AssertionError('connect barrier did not observe one pending SYN')
            flow['handshake_released'] = True
            packet, pseudo = flow['syn_packet']
            super()._receive_tcp(packet, pseudo)
            flow['report']['pending_syn_observed'] = True

    def release_window(self, port, queued):
        with self.protocol_lock:
            flow = self.flows[port]
            if (not flow['challenge_sent'] or flow['released'] or flow['fin_seen'] or
                    len(flow['request']) != 32 or not 0 < queued <= 32768):
                raise AssertionError('readiness barrier lacks a full guest send queue behind window zero')
            flow['count'] = queued
            flow['report']['window_barrier'] = {'advertised_window': 0, 'accepted_bytes': queued,
                                               'queued_data_bytes_received': 0}
            flow['barrier_seen'] = flow['released'] = True
            self._tcp(port, flow)
