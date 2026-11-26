#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the N4 private DNS lifecycle profile against an isolated loopback peer."""

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from boot_smoke import Guest
from make_work_disk import create_fat32
from net_tcp_window_peer import TcpWindowPeer, checksum
from process_smoke import command, resources
from task_smoke import send_bytes


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def wire_name(name):
    return b''.join(bytes((len(label),)) + label.encode('ascii') for label in name.split('.')) + b'\0'


def captured_dns_queries(path):
    capture = path.read_bytes()
    byte_order = {b'\xd4\xc3\xb2\xa1': '<', b'\xa1\xb2\xc3\xd4': '>'}.get(capture[:4])
    if len(capture) < 24 or not byte_order or struct.unpack_from(byte_order + 'I', capture, 20)[0] != 1:
        raise ValueError('expected an Ethernet PCAP from the guest')
    position, queries = 24, 0
    while position < len(capture):
        if len(capture) - position < 16:
            raise ValueError('truncated Ethernet capture record')
        size = struct.unpack_from(byte_order + 'I', capture, position + 8)[0]
        start = position + 16
        position = start + size
        if position > len(capture):
            raise ValueError('truncated Ethernet capture frame')
        frame = capture[start:position]
        if len(frame) < 42 or frame[12:14] != b'\x08\x00' or frame[23] != 17:
            continue
        udp = 14 + (frame[14] & 15) * 4
        if udp >= 34 and udp + 8 <= len(frame) and frame[udp + 2:udp + 4] == b'\x00\x35':
            queries += 1
    return queries


CACHE, CANCEL, STOP = (wire_name(f'{label}.n4.test') for label in ('cache', 'cancel', 'stop'))


class DNSPeer(TcpWindowPeer):
    def __init__(self):
        hosts = secrets.SystemRandom().sample(range(1, 255), 3)
        self.addresses = [f'192.0.2.{host}' for host in hosts]
        self.queries = []
        super().__init__()

    def _receive_udp(self, packet, pseudo):
        if len(packet) < 20 or checksum(pseudo + packet):
            raise ValueError('invalid DNS fixture UDP input')
        source, target, length, _ = struct.unpack('!HHHH', packet[:8])
        if target != 53 or source < 1024 or length != len(packet):
            raise ValueError('unexpected DNS fixture endpoints')
        query = packet[8:]
        txid, flags, questions, answers, authority, additional = struct.unpack('!HHHHHH', query[:12])
        if (flags, questions, answers, authority, additional) != (0x100, 1, 0, 0, 0):
            raise ValueError('unexpected DNS question header')
        qname = query[12:-4]
        if query[-4:] != b'\0\x01\0\x01' or qname not in (CACHE, CANCEL, STOP):
            raise ValueError('unexpected DNS question name or type')
        index = len(self.queries)
        if index >= 4 or qname != (CACHE, CACHE, CANCEL, STOP)[index]:
            raise ValueError('unexpected repeated or reordered DNS request')
        self.queries.append({'question_sha256': hashlib.sha256(query[12:]).hexdigest(),
                             'source_port': source, 'transaction_id': txid})
        if qname == CACHE:
            addresses = ((self.addresses[0], 30), (self.addresses[2], 1)) if index == 0 else ((self.addresses[1], 30),)
            header = struct.pack('!HHHHHH', txid, 0x8180, 1, len(addresses), 0, 0)
            records = b''.join(struct.pack('!HHHIH4s', 0xc00c, 1, 1, ttl, 4, socket.inet_aton(value))
                               for value, ttl in addresses)
            self._udp(53, source, header + query[12:] + records)


def verify_system(system):
    path = system / 'manifest.json'
    manifest = json.loads(path.read_bytes())
    if not json.loads((system / 'net_lwip_inputs.json').read_bytes()).get('dns_probe'):
        raise ValueError('the input system lacks the DNS probe profile')
    for name, expected in manifest['sources'].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f'system source differs from the running tree: {name}')
    for name, artifact in manifest['artifacts'].items():
        if digest(system / name) != artifact['sha256']:
            raise ValueError(f'system artifact mismatch: {name}')
    return manifest['build_id'], digest(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    system = args.system.resolve()
    report = {'status': 'failed', 'runner_sha256': digest(Path(__file__)),
              'peer_transport_sha256': digest(Path(sys.modules[TcpWindowPeer.__module__].__file__))}
    try:
        build_id, manifest_digest = verify_system(system)
        image = system / 'xos-install.iso'
        report.update(build_id=build_id, system_manifest_sha256=manifest_digest, iso_sha256=digest(image),
                      lwip_inputs_sha256=digest(system / 'net_lwip_inputs.json'),
                      sdk_manifest_sha256=digest(system / 'sdk/manifest.json'),
                      network_service_sha256=digest(system / 'user_net_service.image.elf'))
        with tempfile.TemporaryDirectory(prefix='xos_dns_guest_') as temp:
            disk = Path(temp) / 'work.img'
            create_fat32(disk, 512)
            peer = DNSPeer()
            guest = None
            try:
                capture = output / 'network.pcap'
                guest = Guest(image, 'n4_dns', work_disk=disk, network=True, network_peer_port=peer.port,
                              network_capture=capture, log_dir=output)
                report['qemu_version'] = subprocess.check_output(
                    [guest.command[0], '--version'], text=True).splitlines()[0]
                guest.expect(b'xos64> ', timeout=45)
                send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=45)
                command(guest, 'demo quiet', b'demo tasks')
                report['resources_cold'] = resources(guest)
                warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=45)
                if b'[net] close=0' not in warmup or b'kind=exited code=0' not in warmup:
                    raise AssertionError('NIC warmup reset failed')
                # The first device grant establishes its persistent reset observer.
                report['resources_before'] = resources(guest)
                serial = command(guest, 'net-dns-probe 41', b'kind=exited code=', timeout=55)
                expected = [f'[net-dns] {key}={value}'.encode()
                            for key, value in zip(('initial', 'refreshed'), peer.addresses[:2], strict=True)]
                expected += [b'[net-dns] shared_cancel=1 cache_hit=1 expired=1 reset=1', b'[net] close=0',
                             b'[net-dns] result=0', b'kind=exited code=0']
                if not all(line in serial for line in expected) or peer.error or len(peer.queries) != 4:
                    raise AssertionError(f'DNS lifecycle or peer mismatch: {serial[-3000:]!r}, {peer.error}, {peer.queries}')
                report['received_answers'] = peer.addresses[:2]
                report['resources_after'] = resources(guest)
                if report['resources_before'] != report['resources_after']:
                    raise AssertionError('DNS probe did not reclaim guest resources')
            finally:
                try:
                    peer.close()
                finally:
                    if guest is not None:
                        guest.close()
            if peer.error or len(peer.queries) != 4:
                raise AssertionError(f'DNS peer did not finish cleanly: {peer.error}, {peer.queries}')
            report['dns_queries'] = peer.queries
            report['captured_dns_queries'] = captured_dns_queries(capture)
            if report['captured_dns_queries'] != len(peer.queries):
                raise AssertionError('DNS packets in the final capture differ from peer observations')
        if verify_system(system) != (build_id, manifest_digest):
            raise AssertionError('system changed during the guest gate')
        report['capture_sha256'] = digest(capture)
        report['serial_sha256'] = digest(output / 'n4_dns_serial.log')
        report['status'] = 'passed_subset'
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
