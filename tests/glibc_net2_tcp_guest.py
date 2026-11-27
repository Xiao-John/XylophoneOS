#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the glibc outbound IPv4 TCP subset against an independent peer."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_glibc_sdk import inputs as sdk_inputs, sha
from glibc_g1_probe import tool_identity
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer
from xypm_format import require
from xypm_sdk_profile import metadata_snapshot, verify_profile

FIXTURES = ROOT / 'tests/fixtures/glibc_net2'
PORT = ROOT / 'src/ports/glibc/sysdeps/xos'
SHARED = ROOT / 'src/shared/include'
APP = '/bin/glibc_net2.elf'


def receive_exact(connection, expected):
    received = bytearray()
    while len(received) < len(expected):
        packet = connection.recv(len(expected) - len(received))
        require(packet, 'peer received premature EOF')
        received.extend(packet)
    require(bytes(received) == expected, 'peer received different bytes')


def serve(server, nonce, challenge):
    connection, _ = server.accept()
    with connection:
        connection.settimeout(25)
        receive_exact(connection, nonce)
        connection.sendall(challenge)
        connection.shutdown(socket.SHUT_WR)
        receive_exact(connection, (nonce * 49)[:1537])
        require(connection.recv(1) == b'', 'peer did not see final client close')


def baseline_restored(guest, baseline):
    for _ in range(20):
        actual = resources(guest)
        if actual == baseline:
            return
        pump(guest, 0.1)
    raise AssertionError(f'resource mismatch: {actual} expected {baseline}')


def run_case(guest, report, baseline, mode, port, nonce=b'', challenge=b''):
    marker = b'GLIBC_NET2_PASS ' + mode.encode()
    invocation = f'exec-file {APP} {mode} {port}'
    if nonce:
        invocation += ' ' + nonce.decode()
    output = command(guest, invocation, b'kind=exited code=', timeout=65)
    exits = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', output)
    require(exits == [(b'exited', b'0')] and output.splitlines().count(marker) == 1,
            f'{invocation} failed: {output!r}')
    if nonce:
        challenge_line = b'GLIBC_NET2_STREAM nonce=' + nonce + b' data=' + challenge.hex().encode()
        require(output.splitlines().count(challenge_line) == 1, 'guest received different bytes')
    baseline_restored(guest, baseline)
    report['cases'].append({'name': mode, 'baseline_after': baseline})


def start_service(guest):
    begin = len(guest.output)
    output = command(guest, 'net-start 41', b'[net-start] pid=', timeout=60)
    guest.expect(b'[net] ready native_v2=1', start=begin, timeout=60)
    match = re.search(rb'\[net-start\] pid=(\d+)', output)
    require(match, 'service PID missing')
    return int(match[1])


def run_guest(image, program, out, report):
    with tempfile.TemporaryDirectory(prefix='xos_glibc_net2_') as folder:
        disk, readback = Path(folder) / 'work.img', Path(folder) / 'readback.elf'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', APP, program)
        transfer(disk, 'export', APP, readback)
        require(sha(readback) == report['elf_sha256'], 'ELF changed on FAT disk')
        guest = Guest(image, 'net2', iso=True, network=True, work_disk=disk, qmp_enabled=False, log_dir=out)
        try:
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output(
                [guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            guest.expect(b'[net] ready native_v2=1', timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            stopped = command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            require(b'[net] close=0' in stopped, 'initial configured service did not close')
            warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
            require(b'[net] close=0' in warmup, 'NIC warmup reset failed')
            quiet = resources(guest)
            report['baseline_without_service'] = quiet
            run_case(guest, report, quiet, 'no_service', 9)
            run_case(guest, report, quiet, 'capacity', 9)
            seen = []
            for cycle in range(2):
                pid = start_service(guest)
                require(pid not in seen, 'service replacement has the same PID')
                seen.append(pid)
                baseline = resources(guest)
                report['services'].append({'pid': pid, 'baseline': baseline})
                if cycle == 0:
                    run_case(guest, report, baseline, 'wrong_pid', 9)
                    run_case(guest, report, baseline, 'denied', 9)
                    with socket.socket() as refused:
                        refused.bind(('127.0.0.1', 0))
                        run_case(guest, report, baseline, 'refused', refused.getsockname()[1])
                for _ in range(2):
                    nonce, challenge = secrets.token_hex(16).encode(), secrets.token_bytes(32)
                    with socket.socket() as server, ThreadPoolExecutor(max_workers=1) as peer:
                        server.bind(('127.0.0.1', 0))
                        server.settimeout(25)
                        server.listen(1)
                        pending = peer.submit(serve, server, nonce, challenge)
                        run_case(guest, report, baseline, 'stream', server.getsockname()[1], nonce, challenge)
                        pending.result()
                    report['cases'][-1].update(nonce=nonce.decode(), reply_hex=challenge.hex(),
                                              tail_bytes=1537, peer_eof=True)
                stopped = command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
                require(b'[net] close=0' in stopped, 'network service did not reset and close')
                baseline_restored(guest, quiet)
        finally:
            guest.close()
            report['serial_sha256'] = sha(out / 'net2_serial.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('system', 'sdk', 'profile', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    system, sdk, profile, out = (path.resolve() for path in (args.system, args.sdk, args.profile, args.output))
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': sha(Path(__file__)), 'services': [], 'cases': []}
    try:
        sdk_manifest, sdk_hash = metadata_snapshot(sdk / 'manifest.json')
        system_manifest, system_hash = metadata_snapshot(system / 'manifest.json')
        profile_document, profile_hash = metadata_snapshot(profile)
        binding = verify_profile(profile_document, 'glibc', sdk)
        require(sdk_manifest['inputs'] == sdk_inputs(), 'SDK sources changed')
        require(system_manifest['sources'] == system_sources(), 'system sources changed')
        require('net_lwip_inputs.json' in system_manifest['artifacts'], 'system is missing locked lwIP')
        for name, entry in system_manifest['artifacts'].items():
            require(sha(system / name) == entry['sha256'], f'system artifact changed: {name}')
        net_inputs, net_inputs_hash = metadata_snapshot(system / 'net_lwip_inputs.json')
        net_profile = net_inputs.get('static_profile', {})
        require(net_profile.get('pci_instance') == 41, 'system lacks configured QEMU NIC launch binding')
        stubs = set(sdk_manifest['stub_functions'])
        require(not {'socket', 'connect', 'send', 'recv'} & stubs, 'TCP implementation missing')
        require({'bind', 'listen', 'accept', 'poll', 'shutdown', 'setsockopt'} <= stubs,
                'unqualified operations changed')
        target = tool_identity('x86_64-elf-g++')
        require(target.get('available') and target['sha256'] == sdk_manifest['tools']['x86_64-elf-g++']['sha256'],
                'wire fixture compiler differs from SDK compiler')
        wire = FIXTURES / 'wire_layout.cpp'
        wire_inputs = (wire, PORT / 'xos_net2_wire.h', SHARED / 'xos/net_service_abi.hpp')
        snapshot = {str(path.relative_to(ROOT)): sha(path) for path in wire_inputs}
        sysroot = sdk / 'sysroot'
        subprocess.run([target['path'], '-std=gnu++20', '-Wall', '-Wextra', '-Werror', '-nostdinc',
                        '-isystem', sysroot / 'usr/include', '-isystem', sysroot / 'usr/lib/compiler-include',
                        '-I', PORT, '-I', SHARED, '-fsyntax-only', wire], check=True)
        program = out / 'net2.elf'
        subprocess.run([sys.executable, ROOT / 'scripts/build_glibc_program.py', '--sdk', sysroot,
                        '--profile', profile, '--source', FIXTURES / 'socket_probe.c', '--output', program],
                       check=True)
        report.update(profile=binding, profile_sha256=profile_hash, sdk_manifest_sha256=sdk_hash,
                      system_manifest_sha256=system_hash, wire_layout_inputs=snapshot,
                      elf_sha256=sha(program), net_lwip_inputs_sha256=net_inputs_hash,
                      network_profile=net_profile,
                      elf_manifest_sha256=sha(out / 'net2.elf.build/manifest.json'))
        image = system / 'xos-install.iso'
        report['image_sha256'] = sha(image)
        run_guest(image, program, out, report)
        require(metadata_snapshot(profile)[1] == profile_hash and verify_profile(profile_document, 'glibc', sdk) == binding,
                'profile or SDK changed during qualification')
        require(sha(image) == report['image_sha256'] and sha(program) == report['elf_sha256']
                and sha(system / 'manifest.json') == system_hash, 'system or ELF changed during qualification')
        report['status'] = 'passed_subset'
    except (Exception, SystemExit) as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS glibc outbound IPv4 TCP, descriptor reuse, and Net2 service lifecycle')


if __name__ == '__main__':
    main()
