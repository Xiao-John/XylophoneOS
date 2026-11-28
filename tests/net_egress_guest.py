#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify sealed egress authority separately from fresh DNS results in a guest."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_net_lifecycle_probe import INPUTS, RESOLVER_FIXTURE
from make_work_disk import create_fat32
from net_dns_probe_guest import captured_dns_queries, digest, wire_name
from net_tcp_window_peer import TcpWindowPeer, checksum, GUEST_IP, HOST_IP
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xos_app import tree_receipt


class EgressPeer(TcpWindowPeer):
    def __init__(self):
        self.nonce = secrets.token_hex(16)
        self.allowed = [socket.inet_aton(f'192.0.2.{n}') for n in secrets.SystemRandom().sample(range(1, 255), 2)]
        self.denied = socket.inet_aton(f'198.51.100.{secrets.randbelow(254) + 1}')
        self.challenges = [secrets.token_bytes(32), secrets.token_bytes(32)]
        self.questions = {wire_name(f'allow-{self.nonce}.n4.test'): 'allow',
                          wire_name(f'deny-{self.nonce}.n4.test'): 'deny'}
        self.transactions = {}
        self.answer_count = {'allow': 0, 'deny': 0}
        self.application_frames = []
        super().__init__()

    def _send_udp(self, address, source, target, data):
        packet = struct.pack('!HHHH', source, target, 8 + len(data), 0) + data
        pseudo = address + GUEST_IP + struct.pack('!BBH', 0, 17, len(packet))
        packet = packet[:6] + struct.pack('!H', checksum(pseudo + packet) or 0xffff) + packet[8:]
        self.ip_id = (self.ip_id + 1) & 0xffff
        header = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(packet), self.ip_id, 0, 64, 17, 0, address, GUEST_IP)
        header = header[:10] + struct.pack('!H', checksum(header)) + header[12:]
        self._emit(0x0800, header + packet)

    def _receive(self, frame):
        if struct.unpack('!H', frame[12:14])[0] != 0x0800:
            return super()._receive(frame)
        ip = frame[14:]
        size = (ip[0] & 15) * 4 if ip else 0
        if len(ip) < 20 or ip[0] >> 4 != 4 or size < 20 or size > len(ip):
            raise ValueError('invalid IPv4 header')
        total = struct.unpack('!H', ip[2:4])[0]
        if not size <= total <= len(ip) or checksum(ip[:size]) or struct.unpack('!H', ip[6:8])[0] & 0x3fff:
            raise ValueError('invalid IPv4 bounds, checksum or fragment')
        if ip[12:16] != GUEST_IP or ip[9] != 17:
            raise ValueError('unexpected application source or transport escaped policy')
        packet = ip[size:total]
        pseudo = GUEST_IP + ip[16:20] + struct.pack('!BBH', 0, 17, len(packet))
        if len(packet) < 8 or checksum(pseudo + packet):
            raise ValueError('invalid UDP checksum or bounds')
        source, target, length, _ = struct.unpack('!HHHH', packet[:8])
        if source < 1024 or length != len(packet):
            raise ValueError('unexpected UDP source or length')
        if ip[16:20] == HOST_IP and target == 53:
            return self._dns(source, packet[8:])
        if ip[16:20] not in self.allowed or target != 41001 or packet[8:] != self.nonce.encode():
            raise ValueError('denied address, port or wrong nonce reached the wire')
        index = self.allowed.index(ip[16:20])
        if index != len(self.application_frames):
            raise ValueError('duplicate application request or stale DNS answer')
        self.application_frames.append({'address': socket.inet_ntoa(ip[16:20]), 'port': target,
                                        'nonce_sha256': hashlib.sha256(packet[8:]).hexdigest()})
        self._send_udp(ip[16:20], target, source, self.challenges[index])

    def _dns(self, source, query):
        if len(query) < 17:
            raise ValueError('short DNS question')
        txid, flags, questions, answers, authority, additional = struct.unpack('!HHHHHH', query[:12])
        name = query[12:-4]
        if ((flags, questions, answers, authority, additional) != (0x100, 1, 0, 0, 0)
                or query[-4:] != b'\0\x01\0\x01' or name not in self.questions):
            raise ValueError('unexpected fresh DNS question')
        key = source, txid, name
        if key in self.transactions:
            record = self.transactions[key]
            record['retries'] += 1
            address = socket.inet_aton(record['answer'])
        else:
            category = self.questions[name]
            index = self.answer_count[category]
            if index >= (2 if category == 'allow' else 1):
                raise ValueError('extra DNS transaction')
            address = self.allowed[index] if category == 'allow' else self.denied
            self.answer_count[category] += 1
            self.transactions[key] = {'category': category, 'answer': socket.inet_ntoa(address),
                'source_port': source, 'transaction_id': txid, 'retries': 0,
                'question_sha256': hashlib.sha256(query[12:]).hexdigest()}
        answer = struct.pack('!HHHIH4s', 0xc00c, 1, 1, 60, 4, address)
        response = struct.pack('!HHHHHH', txid, 0x8180, 1, 1, 0, 0) + query[12:] + answer
        self._send_udp(HOST_IP, 53, source, response)


def validate(system, fixtures):
    manifest = json.loads((system / 'manifest.json').read_text())
    receipt = json.loads((fixtures / 'receipt.json').read_text())
    network = json.loads((system / 'net_lwip_inputs.json').read_text())
    profile = network.get('static_profile', {})
    expected = [{'cidr': '192.0.2.0/24', 'protocol': 'udp', 'ports': [41001, 41001]}]
    if network.get('dns_probe') or profile.get('revision') != 2 or profile.get('egress') != expected:
        raise ValueError('guest needs the explicit sealed egress profile')
    if profile.get('resolver') != '10.0.2.2' or profile.get('pci_instance') != 41:
        raise ValueError('guest resolver or NIC differs from the private fixture')
    for name, expected in manifest['sources'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('changed system source: ' + name)
    for name, artifact in manifest['artifacts'].items():
        if digest(system / name) != artifact['sha256']:
            raise ValueError('changed system artifact: ' + name)
    if receipt['sources'] != {name: digest(ROOT / name) for name in (RESOLVER_FIXTURE, *INPUTS[2:])}:
        raise ValueError('fixture source mismatch')
    if receipt['sdk_tree_sha256'] != tree_receipt(system / 'sdk')[0] or receipt['libc_linked']:
        raise ValueError('fixture ABI mismatch')
    if digest(fixtures / 'net_resolver_probe.elf') != receipt['artifacts']['net_resolver_probe.elf']:
        raise ValueError('fixture ELF mismatch')
    return {'build_id': manifest['build_id'], 'system_manifest_sha256': digest(system / 'manifest.json'),
            'sdk_tree_sha256': receipt['sdk_tree_sha256'], 'network_profile': profile}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system, fixtures, out = (p.resolve() for p in (args.system, args.fixtures, args.output))
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': digest(Path(__file__)), 'dash_shell': 'not_run'}
    try:
        report.update(validate(system, fixtures))
        image, binary = system / 'xos-install.iso', fixtures / 'net_resolver_probe.elf'
        report.update(image_sha256=digest(image), elf_sha256=digest(binary))
        with tempfile.TemporaryDirectory(prefix='xos_egress_guest_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin'); transfer(disk, 'import', '/bin/policy.elf', binary)
            peer = EgressPeer(); guest = None
            try:
                guest = Guest(image, 'egress', iso=True, work_disk=disk, network=True, qmp_enabled=False,
                              network_peer_port=peer.port, network_capture=out / 'network.pcap', log_dir=out)
                report['qemu_command'] = guest.command
                report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
                guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=60); guest.expect(b'[net] ready native_v2=1', timeout=60)
                command(guest, 'demo quiet', b'demo tasks'); command(guest, 'audio stop', b'audio: service stopped')
                command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
                command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
                report['resources_before'] = resources(guest)
                first = len(guest.output)
                launched = command(guest, 'net-start 41', b'[net-start] pid=', timeout=60)
                service = int(re.search(rb'\[net-start\] pid=(\d+)', launched)[1])
                guest.expect(b'[net] ready native_v2=1', start=first, timeout=60)
                report['resources_with_service'] = resources(guest)
                first = len(guest.output)
                launched = command(guest, f'spawn-file /bin/policy.elf policy {service} {peer.nonce}', b'[loader] started pid=', timeout=30)
                process = int(re.search(rb'\[loader\] started pid=(\d+)', launched)[1])
                guest.expect(b'EGRESS_AWAIT_EPOCH', start=first, timeout=30)
                command(guest, 'net-dns-configure off', b'[net-dns-config] epoch=2')
                command(guest, 'net-dns-configure on', b'[net-dns-config] epoch=3')
                command(guest, f'wait {process}', b'kind=exited code=0', timeout=30)
                output = bytes(guest.output[first:])
                for i in range(2):
                    marker = f'EGRESS_CHALLENGE round={i} address={int.from_bytes(peer.allowed[i], "big")} data={peer.challenges[i].hex()}'.encode()
                    if marker not in output:
                        raise AssertionError('guest did not receive the independent fresh UDP challenge')
                if b'EGRESS_POLICY_PASS' not in output or peer.error or len(peer.application_frames) != 2:
                    raise AssertionError('egress peer did not verify exactly two admitted requests: ' + str(peer.error))
                if resources(guest) != report['resources_with_service']:
                    raise AssertionError('application retained resources')
                command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
                report['resources_after'] = resources(guest)
                if report['resources_after'] != report['resources_before']:
                    raise AssertionError('network service retained resources')
                report.update(nonce=peer.nonce, denied_address=socket.inet_ntoa(peer.denied),
                              transactions=list(peer.transactions.values()), application_frames=peer.application_frames,
                              challenges=[value.hex() for value in peer.challenges], epochs=[1, 2, 3])
            finally:
                peer.close()
                if guest is not None:
                    guest.close()
            if peer.error or peer.answer_count != {'allow': 2, 'deny': 1}:
                raise AssertionError('wrong final DNS transaction counts: ' + str(peer.error))
        report['captured_dns_queries'] = captured_dns_queries(out / 'network.pcap')
        if report['captured_dns_queries'] != sum(item['retries'] + 1 for item in report['transactions']):
            raise AssertionError('capture differs from observed DNS traffic')
        if validate(system, fixtures)['system_manifest_sha256'] != report['system_manifest_sha256']:
            raise AssertionError('inputs changed during qualification')
        report.update(status='passed_subset', capture_sha256=digest(out / 'network.pcap'),
                      serial_sha256=digest(out / 'egress_serial.log'))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS sealed egress tuples, fresh DNS without implicit authority, epoch invalidation and real UDP')


if __name__ == '__main__':
    main()
