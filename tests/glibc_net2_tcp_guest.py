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
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_glibc_sdk import inputs as sdk_inputs, sha
from glibc_g1_probe import tool_identity
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from net_readiness_window_peer import readiness_window_peer
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


def serve(server, nonce, challenge, half_close=False):
    connection, _ = server.accept()
    with connection:
        connection.settimeout(25)
        receive_exact(connection, nonce)
        if half_close:
            require(connection.recv(1) == b'', 'peer did not see SHUT_WR before response')
            connection.sendall(challenge)
            connection.shutdown(socket.SHUT_WR)
            return
        connection.sendall(challenge)
        connection.shutdown(socket.SHUT_WR)
        receive_exact(connection, (nonce * 49)[:1537])
        require(connection.recv(1) == b'', 'peer did not see final client close')


def shutdown_owner_peer(server, nonce, challenge):
    connection, _ = server.accept()
    with connection:
        connection.settimeout(25)
        receive_exact(connection, nonce)
        connection.sendall(challenge)
        receive_exact(connection, b'ok')
        require(connection.recv(1) == b'', 'authorized shutdown owner omitted FIN')


def extended_peer(server, mode, nonce, challenge):
    if mode == 'deferred_release':
        for _ in range(2):
            connection, _ = server.accept()
            with connection:
                connection.settimeout(25)
                require(connection.recv(1) == b'', 'deferred release peer received unexpected payload')
        return
    connection, _ = server.accept()
    with connection:
        connection.settimeout(25)
        if mode == 'concurrent_close':
            time.sleep(0.2)
            try:
                connection.sendall(b'late-original-socket')
                connection.recv(1)
            except (ConnectionResetError, BrokenPipeError):
                pass
            return
        receive_exact(connection, nonce)
        connection.sendall(challenge)
        if mode == 'read_close':
            require(connection.recv(1) == b'', 'read shutdown destroyed the write half')
        else:
            require(connection.recv(1) == b'', 'nonblocking peer did not observe client FIN')


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
    if nonce and mode in ('stream', 'legacy_wait', 'half_close'):
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


def run_guest(image, program, stalled_peer, page_probe, out, report, legacy_kernel=False):
    with tempfile.TemporaryDirectory(prefix='xos_glibc_net2_') as folder:
        disk, readback = Path(folder) / 'work.img', Path(folder) / 'readback.elf'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'mkdir', '/tmp')
        transfer(disk, 'import', APP, program)
        transfer(disk, 'import', '/bin/net2_stall.elf', stalled_peer)
        transfer(disk, 'import', '/bin/net2_page.elf', page_probe)
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
            if not legacy_kernel: run_case(guest, report, quiet, 'pipe_poll', 9)
            if not legacy_kernel:
                begin = len(guest.output)
                launched = command(guest, 'spawn-file /bin/net2_stall.elf', b'[loader] started pid=', timeout=20)
                matched = re.search(rb'\[loader\] started pid=(\d+)', launched)
                require(matched, 'stalled peer PID missing')
                stalled_pid = int(matched[1])
                guest.expect(b'NET2_STALL_READY', start=begin, timeout=20)
                completed = command(guest, f'exec-file {APP} stall 9 {stalled_pid}', b'kind=exited code=', timeout=20)
                require(b'GLIBC_NET2_PASS stall' in completed and b'kind=exited code=0' in completed,
                        'stalled live peer broke caller deadline or late-reply recovery')
                elapsed = re.search(rb'GLIBC_NET2_POLL_TIMEOUT elapsed_ns=(\d+)', completed)
                require(elapsed and 40000000 <= int(elapsed[1]) < 700000000, 'poll timeout was silently extended')
                waited = command(guest, f'wait {stalled_pid}', b'[wait]', timeout=20)
                require(f'[wait] pid={stalled_pid} kind=exited code=0'.encode() in waited,
                        'stalled peer did not consume exactly one capability/readiness request')
                require(b'NET2_STALL_SERVICE_PASS capabilities=1 readiness=1' in bytes(guest.output)[begin:],
                        'read-only query was replayed or connection could not close after late reply')
                baseline_restored(guest, quiet)
                report['cases'].append({'name': 'live_peer_stalled_reply', 'poll_timeout_ms': 40,
                    'actual_elapsed_ns': int(elapsed[1]), 'peer_delay_ms': 1000,
                    'capability_requests': 1, 'readiness_requests': 1, 'late_reply_recovered': True,
                    'baseline_after': quiet})
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
                    detached = command(guest, f'exec-file /bin/net2_page.elf {pid} detach', b'kind=exited code=', timeout=15)
                    require(b'NET_READINESS_PAGE_PASS' in detached and b'kind=exited code=0' in detached, 'grant page target ownership/detach failed')
                    baseline_restored(guest, baseline)
                    report['cases'].append({'name': 'read_only_page_ownership_and_detach', 'baseline_after': baseline})
                    quota = command(guest, f'exec-file /bin/net2_page.elf {pid} quota', b'kind=exited code=', timeout=15)
                    require(b'NET_READINESS_PAGE_PASS' in quota and b'kind=exited code=0' in quota,
                            'grant page target quota recovery failed')
                    baseline_restored(guest, baseline)
                    report['cases'].append({'name': 'read_only_page_delegate_quota_recovery', 'baseline_after': baseline})
                    first = len(guest.output)
                    holder = command(guest, f'spawn-file /bin/net2_page.elf {pid} hold', b'[loader] started pid=', timeout=15)
                    holder_pid = int(re.search(rb'\[loader\] started pid=(\d+)', holder)[1])
                    guest.expect(b'NET_READINESS_PAGE_HOLD grant=', start=first, timeout=15)
                    guest.expect(b'\n', start=guest.output.index(b'NET_READINESS_PAGE_HOLD grant=', first), timeout=10)
                    grant = int(re.search(rb'NET_READINESS_PAGE_HOLD grant=(\d+)\n', guest.output[first:])[1])
                    foreign = command(guest, f'exec-file /bin/net2_page.elf {grant} foreign', b'kind=exited code=', timeout=15)
                    require(b'NET_READINESS_FOREIGN_PASS' in foreign and b'kind=exited code=0' in foreign,
                            'foreign process obtained readiness mapping')
                    command(guest, f'wait {holder_pid}', b'kind=exited code=0', timeout=10)
                    require(b'NET_READINESS_OWNER_EXIT_PASS' in guest.output[first:], 'grant owner exit did not run')
                    baseline_restored(guest, baseline)
                    report['cases'].append({'name': 'read_only_page_foreign_denial_and_owner_exit', 'baseline_after': baseline})
                    nonce, challenge = secrets.token_hex(16).encode(), secrets.token_bytes(32)
                    with socket.socket() as server, ThreadPoolExecutor(max_workers=1) as peer:
                        server.bind(('127.0.0.1', 0)); server.settimeout(25); server.listen(1)
                        pending = peer.submit(shutdown_owner_peer, server, nonce, challenge)
                        first = len(guest.output)
                        owner = command(guest, f'spawn-file /bin/net2_page.elf {pid} socket_owner {server.getsockname()[1]} {nonce.decode()}',
                                        b'[loader] started pid=', timeout=15)
                        owner_pid = int(re.search(rb'\[loader\] started pid=(\d+)', owner)[1])
                        guest.expect(b'NET_SHUTDOWN_OWNER handle=', start=first, timeout=15)
                        guest.expect(b'\n', start=guest.output.index(b'NET_SHUTDOWN_OWNER handle=', first), timeout=10)
                        handle = int(re.search(rb'NET_SHUTDOWN_OWNER handle=(\d+)\n', guest.output[first:])[1])
                        foreign = command(guest, f'exec-file /bin/net2_page.elf {pid} socket_foreign {handle}',
                                          b'kind=exited code=0', timeout=15)
                        require(b'NET_SHUTDOWN_FOREIGN_PASS' in foreign, 'foreign shutdown/UDP negative cases failed')
                        command(guest, f'wait {owner_pid}', b'kind=exited code=0', timeout=15)
                        require(b'NET_SHUTDOWN_OWNER_PASS' in guest.output[first:] and
                                b'NET_SHUTDOWN_DATA data=' + challenge.hex().encode() in guest.output[first:],
                                'foreign attempt affected the owned real TCP exchange')
                        pending.result()
                    baseline_restored(guest, baseline)
                    report['cases'].append({'name': 'shutdown_owner_foreign_and_UDP_rejection',
                        'nonce': nonce.decode(), 'reply_hex': challenge.hex(), 'baseline_after': baseline})
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
                        run_case(guest, report, baseline, 'legacy_wait' if legacy_kernel else 'stream',
                                 server.getsockname()[1], nonce, challenge)
                        pending.result()
                    report['cases'][-1].update(nonce=nonce.decode(), reply_hex=challenge.hex(),
                                              tail_bytes=1537, peer_eof=True)
                if not legacy_kernel:
                    nonce, challenge = secrets.token_hex(16).encode(), secrets.token_bytes(32)
                    with socket.socket() as server, ThreadPoolExecutor(max_workers=1) as peer:
                        server.bind(('127.0.0.1', 0)); server.settimeout(25); server.listen(1)
                        pending = peer.submit(serve, server, nonce, challenge, True)
                        run_case(guest, report, baseline, 'half_close', server.getsockname()[1], nonce, challenge)
                        pending.result()
                    report['cases'][-1].update(nonce=nonce.decode(), reply_hex=challenge.hex(),
                                              peer_eof_before_response=True, readiness_timeout_ms=30)
                if not legacy_kernel and cycle == 0:
                    with socket.socket() as refused:
                        refused.bind(('127.0.0.1', 0))
                        run_case(guest, report, baseline, 'nonblocking_refused', refused.getsockname()[1])
                    close_round = 0
                    for mode in ('nonblocking', 'read_close', *(('concurrent_close',) * 20), 'deferred_release'):
                        case_begin = len(guest.output)
                        nonce, challenge = secrets.token_hex(16).encode(), secrets.token_bytes(32)
                        with socket.socket() as server, ThreadPoolExecutor(max_workers=1) as peer:
                            server.bind(('127.0.0.1', 0)); server.settimeout(25); server.listen(1)
                            pending = peer.submit(extended_peer, server, mode, nonce, challenge)
                            run_case(guest, report, baseline, mode, server.getsockname()[1],
                                     nonce if mode not in ('concurrent_close', 'deferred_release') else b'', challenge)
                            pending.result()
                        if mode == 'concurrent_close':
                            close_round += 1
                            case_output = bytes(guest.output)[case_begin:]
                            require(b'GLIBC_NET2_POLL_PENDING threads=2 blocked=1' in case_output,
                                    'concurrent close lacked an actual pending poll observation')
                            require(b'GLIBC_NET2_CLOSE_IDENTITY' in case_output,
                                    'original description identity was not retained')
                            observed = re.search(rb'GLIBC_NET2_CLOSE_RESULT result=(-?\d+) error=(\d+) revents=(\d+) elapsed_ns=(\d+)', case_output)
                            require(observed and int(observed[1]) == 1 and int(observed[3]) == 32,
                                    'concurrent close returned a stale event or transient lock error')
                            report['cases'][-1].update(round=close_round, poll_result=int(observed[1]),
                                errno=int(observed[2]), revents=int(observed[3]), elapsed_ns=int(observed[4]))
                        report['cases'][-1].update(real_peer=True)
                if not legacy_kernel and cycle == 1:
                    begin = len(guest.output)
                    spawned = command(guest, f'spawn-file /bin/net2_page.elf {pid} service_exit', b'[loader] started pid=', timeout=15)
                    page_pid = int(re.search(rb'\[loader\] started pid=(\d+)', spawned)[1])
                    guest.expect(b'NET_READINESS_PAGE_WAITING_FOR_SERVICE_EXIT', start=begin, timeout=15)
                stopped = command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
                require(b'[net] close=0' in stopped, 'network service did not reset and close')
                if not legacy_kernel and cycle == 1:
                    page_wait = command(guest, f'wait {page_pid}', b'[wait]', timeout=15)
                    require(b'kind=exited code=0' in page_wait and b'NET_READINESS_PAGE_PASS' in bytes(guest.output)[begin:], 'grant mapping did not survive service exit safely')
                    report['cases'].append({'name': 'read_only_page_service_exit', 'baseline_after': quiet})
                baseline_restored(guest, quiet)
        finally:
            guest.close()
            report['serial_sha256'] = sha(out / 'net2_serial.log')


def run_window_guest(image, program, out, report):
    peer = readiness_window_peer()
    guest = None
    capture = out / 'readiness_window.pcap'
    nonce, challenge = secrets.token_hex(16), secrets.token_bytes(32)
    port, evidence = peer.begin(nonce, challenge)
    report['window_peer'] = evidence
    try:
        with tempfile.TemporaryDirectory(prefix='xos_glibc_readiness_') as folder:
            disk = Path(folder) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', APP, program)
            guest = Guest(image, 'readiness_window', iso=True, network=True, work_disk=disk,
                          network_peer_port=peer.port, network_capture=capture, qmp_enabled=False, log_dir=out)
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
            baseline = resources(guest)
            start_service(guest)
            begin = len(guest.output)
            launched = command(guest, f'spawn-file {APP} window {port} {nonce}', b'[loader] started pid=', timeout=20)
            pid = int(re.search(rb'\[loader\] started pid=(\d+)', launched)[1])
            guest.expect(b'GLIBC_NET2_CONNECT_PENDING', start=begin, timeout=20)
            peer.release_handshake(port)
            guest.expect(b'GLIBC_NET2_WINDOW_BLOCKED queued=', start=begin, timeout=20)
            guest.expect(b'\n', start=guest.output.index(b'GLIBC_NET2_WINDOW_BLOCKED queued=', begin), timeout=5)
            queued = int(re.search(rb'GLIBC_NET2_WINDOW_BLOCKED queued=(\d+)\n', guest.output[begin:])[1])
            peer.release_window(port, queued)
            completed = command(guest, f'wait {pid}', b'kind=exited code=', timeout=20)
            require(b'kind=exited code=0' in completed and b'GLIBC_NET2_PASS window' in guest.output[begin:],
                    'controlled readiness peer probe failed')
            peer.finish(port, timeout=15)
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            baseline_restored(guest, baseline)
            report['cases'].append({'name': 'controlled_pending_connect_and_window_recovery',
                                    'baseline_after': baseline, 'queued_bytes': queued})
    finally:
        peer.close()
        if guest is not None:
            guest.close()
    require(not peer.error, 'controlled readiness packet peer failed: ' + str(peer.error))
    report['window_capture_sha256'] = sha(capture)
    report['window_serial_sha256'] = sha(out / 'readiness_window_serial.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('system', 'sdk', 'profile', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--legacy-kernel', action='store_true',
                        help='require deadline modes to fail closed while old blocking TCP stays usable')
    args = parser.parse_args()
    system, sdk, profile, out = (path.resolve() for path in (args.system, args.sdk, args.profile, args.output))
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': sha(Path(__file__)), 'services': [], 'cases': [],
              'deadline_profile': 'legacy_kernel_fail_closed' if args.legacy_kernel else 'absolute_ipc_wait',
              'zero_timeout_connected_socket': 'grant_level_snapshot_fresh_negative_or_eagain', 'posix_complete_poll': False}
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
        require(not {'socket', 'connect', 'send', 'recv', 'poll', 'shutdown'} & stubs, 'TCP implementation missing')
        require({'bind', 'listen', 'accept', 'setsockopt'} <= stubs,
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
        stalled_peer = out / 'net2_stall.elf'
        native_sdk = system / 'sdk'
        subprocess.run([target['path'], '-std=c++17', '-Os', '-Wall', '-Wextra', '-Werror',
                        '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-stack-protector',
                        '-fno-pie', '-fno-pic', '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++',
                        '-ffunction-sections', '-fdata-sections', '-I', native_sdk / 'include',
                        FIXTURES / 'stall_service.cpp', '-nostdlib', '-static', '-no-pie',
                        '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                        '-T', native_sdk / 'user.ld', native_sdk / 'crt0.o', native_sdk / 'lib/libxos.a',
                        '-o', stalled_peer], check=True)
        report['stalled_peer'] = {'elf_sha256': sha(stalled_peer),
            'source_sha256': sha(FIXTURES / 'stall_service.cpp'),
            'purpose': 'test-only authenticated IPC peer; no actual network service qualification'}
        page_probe = out / 'net2_page.elf'
        page_source = ROOT / 'tests/fixtures/network/readiness_page_probe.cpp'
        subprocess.run([target['path'], '-std=c++17', '-Os', '-Wall', '-Wextra', '-Werror',
                        '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-stack-protector',
                        '-fno-pie', '-fno-pic', '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++',
                        '-ffunction-sections', '-fdata-sections', '-I', native_sdk / 'include',
                        page_source, '-nostdlib', '-static', '-no-pie',
                        '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                        '-T', native_sdk / 'user.ld', native_sdk / 'crt0.o', native_sdk / 'lib/libxos.a',
                        '-o', page_probe], check=True)
        report['page_probe'] = {'elf_sha256': sha(page_probe), 'source_sha256': sha(page_source)}
        run_guest(image, program, stalled_peer, page_probe, out, report, args.legacy_kernel)
        if not args.legacy_kernel:
            run_window_guest(image, program, out, report)
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
