#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the WebCore DNS queue with the native Net2 service and an isolated peer."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import socket
import subprocess
import tempfile

from net_resolver_guest import (
    Guest, ResolverPeer, ROOT, captured_dns_queries, command, create_fat32,
    digest, resources, send_bytes, transfer, wire_name,
)


FIXTURE = 'tests/fixtures/webkit/xos_webcore_resolver.cpp'
SOFTWARE_LOCK = 'src/ports/webkit/page/source_lock.json'
NET2_HEADERS = (
    'src/shared/include/xos/net_service_abi.hpp',
    'src/user/include/xos/net_service_client.hpp',
    'src/user/include/xos/net_transport.hpp',
)
EXPECTED_NAMES = ('pair.n4.test', 'missing.n4.test', 'cancelled.n4.test')


def verify_inputs(args):
    manifest_path = args.system / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    if not json.loads((args.system / 'net_lwip_inputs.json').read_bytes()).get('dns_probe'):
        raise ValueError('the guest system requires the DNS probe profile')
    for name, expected in manifest['sources'].items():
        if digest(args.system_source / name) != expected:
            raise ValueError(f'system source differs from the build receipt: {name}')
    for name, artifact in manifest['artifacts'].items():
        if digest(args.system / name) != artifact['sha256']:
            raise ValueError(f'system artifact differs from the build receipt: {name}')

    receipts = json.loads(args.receipt.read_bytes())
    inputs = {
        'elf_sha256': digest(args.elf),
        'fixture_sha256': digest(ROOT / FIXTURE),
        'software_source_lock_sha256': digest(args.webcore_source / SOFTWARE_LOCK),
        'net2_headers': {name: digest(args.webcore_source / name) for name in NET2_HEADERS},
    }
    if any(receipts[key] != value for key, value in inputs.items()):
        raise ValueError('the resolver ELF, fixture, or sources differ from the link receipt')
    return {
        'build_id': manifest['build_id'],
        'system_manifest_sha256': digest(manifest_path),
        'sdk_manifest_sha256': digest(args.system / 'sdk/manifest.json'),
        'iso_sha256': digest(args.system / 'xos-install.iso'),
        'link_receipt_sha256': digest(args.receipt),
        **inputs,
    }


def assert_exit(output, marker):
    if output.count(marker) != 1 or re.findall(rb'kind=exited code=(\d+)', output) != [b'0']:
        raise AssertionError(f'guest expected {marker!r}: {output[-1800:]!r}')


def exercise(guest, peer, report):
    guest.expect(b'xos64> ', timeout=45)
    send_bytes(guest, b'run\r')
    guest.expect_supervisor(trace=True, timeout=45)
    command(guest, 'demo quiet', b'demo tasks')
    warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=45)
    assert_exit(warmup, b'[net] close=0')
    report['resources_before'] = resources(guest)

    start = len(guest.output)
    launched = command(guest, 'net-start 41', b'[net-start] pid=', timeout=45)
    service = re.search(rb'\[net-start\] pid=(\d+)', launched)
    if service is None:
        raise AssertionError(f'guest did not return the Net2 process identity: {launched!r}')
    pid = int(service[1])
    guest.expect(b'[net] ready native_v2=1', start=start, timeout=45)
    command(guest, 'net-dns-configure on', b'[net-dns-config] epoch=2')

    cases = {}
    report['cases'] = cases
    fixture = 'exec-file /bin/webdns.elf'
    wrong = command(guest, f'{fixture} wrong-pid {pid + 1}', b'kind=exited code=', timeout=45)
    assert_exit(wrong, b'XOS_WEBCORE_RESOLVER_DENIED_OK mode=wrong-pid')
    cases['wrong_service_pid'] = 'passed'

    answer = int.from_bytes(socket.inet_aton(peer.addresses[0]), 'big')
    peer.release.set()
    live = command(guest, f'{fixture} live {pid} {answer}', b'kind=exited code=', timeout=65)
    assert_exit(live, f'XOS_WEBCORE_RESOLVER_LIVE_OK answer={answer} nxdomain=1 cancelled=1 reused=1'.encode())
    cases['answer_nxdomain_single_cancel_and_id_reuse'] = 'passed'
    report['answer'] = peer.addresses[0]

    command(guest, 'net-dns-configure off', b'[net-dns-config] epoch=3')
    command(guest, 'net-stop', b'[net] close=0', timeout=45)
    stopped = command(guest, f'{fixture} stopped {pid}', b'kind=exited code=', timeout=45)
    assert_exit(stopped, b'XOS_WEBCORE_RESOLVER_DENIED_OK mode=stopped')
    cases['stopped_service'] = 'passed'
    report['resources_after'] = resources(guest)
    if report['resources_after'] != report['resources_before']:
        raise AssertionError('resolver guests or native service did not reclaim resources')


def verify_wire(peer, capture, report):
    records = list(peer.transactions.values())
    report['transactions'] = records
    expected = Counter(sha256(wire_name(name) + b'\x00\x01\x00\x01').hexdigest() for name in EXPECTED_NAMES)
    actual = Counter(record['question_sha256'] for record in records)
    if peer.error or peer.pairs != 1 or actual != expected:
        raise AssertionError(f'isolated DNS questions differ from the fixture: {peer.error}, {records}')
    report['captured_dns_queries'] = captured_dns_queries(capture)
    if report['captured_dns_queries'] != sum(record['retries'] + 1 for record in records):
        raise AssertionError('the final packet capture differs from the observed DNS questions')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'elf', 'receipt', 'webcore-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--system-source', type=Path, default=ROOT)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': digest(Path(__file__))}
    capture = output / 'network.pcap'
    try:
        inputs = verify_inputs(args)
        report.update(inputs)
        image = args.system / 'xos-install.iso'
        with tempfile.TemporaryDirectory(prefix='xos_webcore_dns_') as temporary:
            disk = Path(temporary) / 'work.img'
            readback = Path(temporary) / 'readback.elf'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/webdns.elf', args.elf)
            transfer(disk, 'export', '/bin/webdns.elf', readback)
            report['fat_readback_sha256'] = digest(readback)
            if report['fat_readback_sha256'] != inputs['elf_sha256']:
                raise ValueError('the fixture staged in the guest differs from the tested ELF')

            peer, guest = ResolverPeer(), None
            try:
                guest = Guest(image, 'webcore_dns', work_disk=disk, network=True,
                              network_peer_port=peer.port, network_capture=capture, log_dir=output)
                report['qemu_version'] = subprocess.check_output(
                    [guest.command[0], '--version'], text=True).splitlines()[0]
                exercise(guest, peer, report)
            finally:
                peer.release.set()
                try:
                    peer.close()
                finally:
                    if guest is not None:
                        guest.close()
            verify_wire(peer, capture, report)

        if verify_inputs(args) != inputs:
            raise AssertionError('resolver build inputs changed during guest execution')
        report['status'] = 'passed_subset'
    finally:
        for name, artifact in (('capture_sha256', capture), ('serial_sha256', output / 'webcore_dns_serial.log')):
            if artifact.is_file():
                report[name] = digest(artifact)
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
