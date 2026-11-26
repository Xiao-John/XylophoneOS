#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Resolve through authenticated net2 sessions on an isolated real guest NIC."""

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
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from boot_smoke import Guest
from build_net_lifecycle_probe import INPUTS, RESOLVER_FIXTURE
from make_work_disk import create_fat32
from net_dns_probe_guest import captured_dns_queries, digest, wire_name
from net_tcp_window_peer import TcpWindowPeer, checksum
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xos_app import tree_receipt


PAIR = wire_name('pair.n4.test')
FLAGS = {wire_name(f'{label}.n4.test'): flags for label, flags in
         (('missing', 0x8183), ('empty', 0x8180), ('failure', 0x8182),
          ('refused', 0x8185), ('truncated', 0x8380), ('silent', None), ('cancelled', None))}


class ResolverPeer(TcpWindowPeer):
    def __init__(self):
        self.addresses = [f'192.0.2.{host}' for host in secrets.SystemRandom().sample(range(1, 255), 2)]
        self.release = threading.Event()
        self.queried = threading.Event()
        self.transactions = {}
        self.pairs = 0
        super().__init__()

    def _receive_udp(self, packet, pseudo):
        if len(packet) < 20 or checksum(pseudo + packet):
            raise ValueError('invalid UDP envelope')
        source, target, length, _ = struct.unpack('!HHHH', packet[:8])
        if target != 53 or source < 1024 or length != len(packet):
            raise ValueError('unexpected UDP endpoints')
        query = packet[8:]
        txid, flags, questions, answers, authority, additional = struct.unpack('!HHHHHH', query[:12])
        if (flags, questions, answers, authority, additional) != (0x100, 1, 0, 0, 0):
            raise ValueError('unexpected DNS fixture query')
        qname = query[12:-4]
        if query[-4:] != b'\0\x01\0\x01' or (qname != PAIR and qname not in FLAGS):
            raise ValueError('unexpected DNS fixture question')
        key = source, txid, qname
        if key in self.transactions:
            self.transactions[key]['retries'] += 1
            return
        self.transactions[key] = {'question_sha256': hashlib.sha256(query[12:]).hexdigest(),
                                  'source_port': source, 'transaction_id': txid, 'retries': 0}
        record, count = b'', 0
        if qname == PAIR:
            self.pairs += 1
            self.queried.set()
            if self.pairs > len(self.addresses) or not self.release.wait(15):
                raise ValueError('missing controller barrier or unexpected new pair query')
            count = 1
            record = struct.pack('!HHHIH4s', 0xc00c, 1, 1, 30, 4,
                                 socket.inet_aton(self.addresses[self.pairs - 1]))
            flags = 0x8180
        else:
            flags = FLAGS[qname]
            if flags is None:
                return
        response = struct.pack('!HHHHHH', txid, flags, 1, count, 0, 0) + query[12:] + record
        self._udp(53, source, response)


def validate(system, fixtures, legacy):
    manifest = json.loads((system / 'manifest.json').read_text())
    receipt = json.loads((fixtures / 'receipt.json').read_text())
    lwip = json.loads((system / 'net_lwip_inputs.json').read_text())
    if bool(lwip.get('dns_probe')) == legacy:
        raise ValueError('select the system built for the requested resolver mode')
    for name, expected in manifest['sources'].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f'changed system source: {name}')
    for name, artifact in manifest['artifacts'].items():
        if digest(system / name) != artifact['sha256']:
            raise ValueError(f'changed system artifact: {name}')
    if receipt['sources'] != {name: digest(ROOT / name) for name in (RESOLVER_FIXTURE, *INPUTS[2:])}:
        raise ValueError('fixture sources changed')
    if receipt['sdk_tree_sha256'] != tree_receipt(system / 'sdk')[0] or receipt['libc_linked']:
        raise ValueError('fixture ABI input mismatch')
    if digest(fixtures / 'net_resolver_probe.elf') != receipt['artifacts']['net_resolver_probe.elf']:
        raise ValueError('fixture artifact mismatch')
    return manifest['build_id'], digest(system / 'manifest.json'), receipt['sdk_tree_sha256']


def spawn(guest, command_line, marker):
    first = len(guest.output)
    response = command(guest, command_line, b'[loader] started pid=', timeout=35)
    process = re.search(rb'\[loader\] started pid=(\d+)', response)
    guest.expect(marker, start=first, timeout=35)
    guest.expect(b'\n', start=guest.output.index(marker, first), timeout=20)
    ticket = re.search(re.escape(marker) + rb'(\d+)\n', guest.output[first:])
    if not process or not ticket:
        raise AssertionError('missing process or ticket identity')
    return int(process[1]), int(ticket[1])


def answer_marker(peer, index, epoch):
    address = int.from_bytes(socket.inet_aton(peer.addresses[index]), 'big')
    return f'N4_ANSWER epoch={epoch} address={address}'.encode()


def exercise(guest, peer, legacy, report):
    guest.expect(b'xos64> ', timeout=45)
    send_bytes(guest, b'run\r')
    guest.expect_supervisor(trace=True, timeout=45)
    command(guest, 'demo quiet', b'demo tasks')
    warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=45)
    if b'[net] close=0' not in warmup:
        raise AssertionError('NIC warmup reset failed')
    report['resources_before'] = resources(guest)
    before = len(guest.output)
    launched = command(guest, 'net-start 41', b'[net-start] pid=', timeout=45)
    service = int(re.search(rb'\[net-start\] pid=(\d+)', launched)[1])
    guest.expect(b'[net] ready native_v2=1', start=before, timeout=45)
    fixture = 'exec-file /bin/n4.elf'
    if legacy:
        result = command(guest, f'{fixture} legacy {service}', b'N4_LEGACY_COMPATIBLE', timeout=45)
        if b'kind=exited code=0' not in result:
            raise AssertionError('legacy compatibility probe failed')
    else:
        result = command(guest, f'{fixture} disabled {service}', b'N4_DISABLED', timeout=45)
        if b'kind=exited code=0' not in result:
            raise AssertionError('initial resolver mode was not disabled')
        command(guest, 'net-dns-configure on', b'[net-dns-config] epoch=2')
        owner, ticket = spawn(guest, f'spawn-file /bin/n4.elf owner {service}', b'N4_OWNER ticket=')
        if not peer.queried.wait(5):
            raise AssertionError('owner query did not reach the fixture')
        joiner, joined = spawn(guest, f'spawn-file /bin/n4.elf join {service} {ticket}', b'N4_JOIN ticket=')
        if owner == joiner or ticket == joined:
            raise AssertionError('resolver sessions or tickets did not separate')
        command(guest, 'net-dns-configure off', b'[net-dns-config] error=-203')
        command(guest, f'kill {owner}', b'kill: accepted')
        command(guest, f'wait {owner}', b'kind=killed')
        joined_at = len(guest.output)
        peer.release.set()
        command(guest, f'wait {joiner}', b'kind=exited code=0', timeout=30)
        if answer_marker(peer, 0, 2) not in guest.output[joined_at:] or peer.pairs != 1:
            raise AssertionError('session termination changed the surviving result or duplicated traffic')
        command(guest, 'net-dns-configure off', b'[net-dns-config] epoch=3')
        command(guest, 'net-dns-configure on', b'[net-dns-config] epoch=4')
        result = command(guest, f'{fixture} fresh {service}', b'kind=exited code=0', timeout=45)
        if answer_marker(peer, 1, 4) not in result or peer.pairs != 2:
            raise AssertionError('configuration epoch did not invalidate the old positive cache')
        result = command(guest, f'{fixture} errors {service}', b'N4_STRUCTURED_RESULTS_PASS', timeout=45)
        if b'kind=exited code=0' not in result:
            raise AssertionError('structured results or cancellation failed')
        report['clients'] = [{'pid': owner, 'ticket': ticket, 'status': 'killed'},
                             {'pid': joiner, 'ticket': joined, 'status': 'resolved'}]
        report['epochs'] = [2, 3, 4]
        report['answers'] = peer.addresses
    command(guest, 'net-stop', b'[net] close=0', timeout=45)
    report['resources_after'] = resources(guest)
    if report['resources_after'] != report['resources_before']:
        raise AssertionError('net2 service leaked guest resources')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--legacy', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    system, fixtures = args.system.resolve(), args.fixtures.resolve()
    report = {'status': 'failed', 'legacy': args.legacy, 'runner_sha256': digest(Path(__file__))}
    try:
        identity = validate(system, fixtures, args.legacy)
        image = system / 'xos-install.iso'
        binary = fixtures / 'net_resolver_probe.elf'
        report.update(build_id=identity[0], system_manifest_sha256=identity[1], sdk_tree_sha256=identity[2],
                      iso_sha256=digest(image), fixture_receipt_sha256=digest(fixtures / 'receipt.json'),
                      payload_sha256=digest(binary))
        with tempfile.TemporaryDirectory(prefix='xos_net_resolver_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/n4.elf', binary)
            peer, guest = ResolverPeer(), None
            capture = output / 'network.pcap'
            try:
                guest = Guest(image, 'resolver', work_disk=disk, network=True, network_peer_port=peer.port,
                              network_capture=capture, log_dir=output)
                report['qemu_version'] = subprocess.check_output(
                    [guest.command[0], '--version'], text=True).splitlines()[0]
                exercise(guest, peer, args.legacy, report)
                if peer.error or len(peer.transactions) != (0 if args.legacy else 9):
                    raise AssertionError(f'unexpected wire transactions: {peer.error}, {peer.transactions}')
            finally:
                peer.release.set()
                try:
                    peer.close()
                finally:
                    if guest is not None:
                        guest.close()
            if peer.error or len(peer.transactions) != (0 if args.legacy else 9):
                raise AssertionError(f'resolver peer did not finish cleanly: {peer.error}, {peer.transactions}')
            report['transactions'] = list(peer.transactions.values())
            report['captured_dns_queries'] = captured_dns_queries(capture)
            if report['captured_dns_queries'] != sum(item['retries'] + 1 for item in report['transactions']):
                raise AssertionError('DNS packets in the final capture differ from peer observations')
        if validate(system, fixtures, args.legacy) != identity:
            raise AssertionError('test inputs changed during the guest run')
        report['capture_sha256'] = digest(capture)
        report['serial_sha256'] = digest(output / 'resolver_serial.log')
        report['status'] = 'passed_subset'
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
