#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Authenticated N2 lifecycle, isolation and reclamation with real XOS processes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import socket
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_net_lifecycle_probe import INPUTS
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--serial-only', action='store_true')
    parser.add_argument('--revoke-rounds', type=int, default=12, choices=range(1, 17))
    args = parser.parse_args()
    system, fixtures, out = args.system.resolve(), args.fixtures.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build'); out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'not_run', 'runner_sha256': sha(Path(__file__)), 'checks': [], 'revocations': [],
              'not_run': ['in_place_driver_crash_recovery_requires_new_device_contract',
                          'unresponsive_device_reset_injection', 'packet_loss_reordering', 'DNS_DHCP_TLS',
                          'deterministic_same_poll_round_revoke_accept_schedule']}
    guest = None

    def verify_inputs():
        for name, digest in manifest['sources'].items():
            if sha(ROOT / name) != digest:
                raise ValueError('system source mismatch: ' + name)
        for name, entry in manifest['artifacts'].items():
            if sha(system / name) != entry['sha256']:
                raise ValueError('system artifact mismatch: ' + name)
        if receipt['sources'] != {name: sha(ROOT / name) for name in INPUTS}:
            raise ValueError('fixture sources mismatch')
        if receipt['sdk_tree_sha256'] != tree_receipt(system / 'sdk')[0] or receipt['libc_linked']:
            raise ValueError('fixture SDK/libc mismatch')
        for name, digest in receipt['artifacts'].items():
            if sha(fixtures / name) != digest:
                raise ValueError('fixture artifact mismatch: ' + name)

    def restored(expected):
        for _ in range(30):
            actual = resources(guest)
            if actual == expected:
                return
            pump(guest, 0.1)
        raise AssertionError(f'resource mismatch: {actual} expected {expected}')

    def info(expected_sessions, expected_connections):
        output = command(guest, 'net-info', b'[net-info] sessions=', timeout=10)
        match = re.search(rb'\[net-info\] sessions=(\d+) connections=(\d+) udp_dropped=(\d+)', output)
        if not match or tuple(map(int, match.groups()[:2])) != (expected_sessions, expected_connections):
            raise AssertionError('service budget mismatch: ' + repr(output))

    def start_service():
        start = len(guest.output)
        output = command(guest, 'net-start 41', b'[net-start] pid=', timeout=60)
        match = re.search(rb'\[net-start\] pid=(\d+)', output)
        if not match:
            raise AssertionError('missing service PID')
        guest.expect(b'[net] ready native_v2=1', start=start, timeout=60)
        return int(match[1])

    def run(mode, marker, suffix='', code=0, timeout=30):
        output = command(guest, f'exec-file /bin/netlife.elf {mode} {service} {suffix}'.rstrip(),
                         marker, timeout=timeout)
        statuses = re.findall(rb'kind=exited code=(-?\d+)', output)
        if not statuses or int(statuses[-1]) != code:
            raise AssertionError(repr(output[-2500:]))
        return output

    def spawn(mode, marker, suffix=''):
        begin = len(guest.output)
        output = command(guest, f'spawn-file /bin/netlife.elf {mode} {service} {suffix}'.rstrip(),
                         b'[loader] started pid=', timeout=20)
        match = re.search(rb'\[loader\] started pid=(\d+)', output)
        if not match:
            raise AssertionError(repr(output))
        pid = int(match[1])
        identity = marker + f' pid={pid} '.encode()
        guest.expect(identity, start=begin, timeout=20)
        # A serial read may end immediately after the PID prefix. Wait for the
        # complete record before parsing fields printed by subsequent writes.
        guest.expect(b'\n', start=guest.output.find(identity, begin), timeout=20)
        data = bytes(guest.output)[begin:]
        row = re.search(re.escape(marker) + rb' pid=(\d+) first=(\d+) second=(\d+)', data)
        if not row:
            raise AssertionError('missing complete fixture identity')
        return pid, int(row[2]), int(row[3]), begin

    def wait(pid, kind=b'exited', code=0):
        output = command(guest, f'wait {pid}', b'[wait]', timeout=20)
        if b'kind=' + kind not in output or (kind == b'exited' and f'code={code}'.encode() not in output):
            raise AssertionError(repr(output))

    try:
        manifest = json.loads((system / 'manifest.json').read_text())
        receipt = json.loads((fixtures / 'receipt.json').read_text())
        verify_inputs()
        if 'net_lwip_inputs.json' not in manifest['artifacts']:
            raise ValueError('system requires locked lwIP backend')
        report.update(build_id=manifest['build_id'], image_sha256=sha(system / 'xos-install.iso'),
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      fixture_receipt_sha256=sha(fixtures / 'receipt.json'),
                      sdk_tree_sha256=receipt['sdk_tree_sha256'], artifacts=receipt['artifacts'])
        with tempfile.TemporaryDirectory(prefix='xos_net_lifecycle_') as temporary:
            disk = Path(temporary) / 'work.img'; create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/netlife.elf', fixtures / 'net_lifecycle_probe.elf')
            transfer(disk, 'import', '/bin/netexec.elf', fixtures / 'net_exec_receiver.elf')
            report['initial_disk_sha256'] = sha(disk)
            guest = Guest(system / 'xos-install.iso', str(out.relative_to(ROOT / 'build')) + '/guest',
                          iso=True, network=True, work_disk=disk, qmp_enabled=not args.serial_only,
                          network_capture=out / 'network.pcap')
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks'); pump(guest, 0.2)
            command(guest, 'audio stop', b'audio: service stopped')
            warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
            if b'[net] close=0' not in warmup:
                raise AssertionError('NIC warmup reset failed')
            before_service = resources(guest)
            service = start_service(); info(1, 0); pump(guest, 0.1)
            baseline = resources(guest); report['baseline'] = baseline
            report['before_service'] = before_service; report['service_pid'] = service

            victim, handle, second, _ = spawn('hold', b'NET_HOLD_READY')
            if handle == second:
                raise AssertionError('duplicate connection handles')
            run('isolation', b'NET_ISOLATION_PASS', f'{handle} {victim}')
            info(2, 2); report['checks'].append('cross_pid_handles_and_controller_operations_denied')
            holders = [victim]
            for _ in range(3):
                holders.append(spawn('hold', b'NET_HOLD_READY')[0])
            info(5, 8)
            run('info', b'NET_LIFECYCLE_FAIL', code=91)
            info(5, 8); report['checks'].append('four_applications_eight_connections_controller_reserved_budget')
            for pid in holders:
                command(guest, f'kill {pid}', b'kill: accepted'); wait(pid, kind=b'killed')
            restored(baseline); info(1, 0)
            report['checks'].append('kill_reclaims_all_application_connections_and_resources')

            for mode, marker in [('cancel', b'NET_CANCEL_PASS'), ('exit', b'NET_EXIT_READY'),
                                 ('exec', b'NET_EXEC_PASS'), ('stall', b'NET_STALL_PASS')]:
                output = run(mode, marker)
                restored(baseline); info(1, 0)
                report['checks'].append(mode + '_reclaims_connections_and_resources')
                if mode == 'stall':
                    report['reply_timeout_ns'] = int(re.search(rb'NET_STALL_PASS pid=\d+ first=(\d+)', output)[1])
            output = command(guest, f'exec-file /bin/netlife.elf fault {service}', b'kind=fault', timeout=30)
            if b'NET_FAULT_READY' not in output:
                raise AssertionError('fault before network connection established')
            restored(baseline); info(1, 0); report['checks'].append('fault_reclaims_connections_and_resources')

            for round_number in range(args.revoke_rounds):
                nonce = secrets.token_hex(16)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
                    server.bind(('127.0.0.1', 0)); server.settimeout(0.2)
                    cancel, release_echo = threading.Event(), threading.Event()
                    exchange = {'round': round_number, 'nonce': nonce, 'echoes': 0}
                    report['revocations'].append(exchange)

                    def echo():
                        try:
                            while not cancel.is_set():
                                try:
                                    data, peer = server.recvfrom(2048)
                                except socket.timeout:
                                    continue
                                if data != nonce.encode():
                                    raise ValueError('revocation echo mismatch')
                                while not release_echo.wait(0.1):
                                    if cancel.is_set():
                                        return
                                server.sendto(data, peer); exchange['echoes'] += 1
                        except OSError as error:
                            if not cancel.is_set():
                                exchange['error'] = str(error)
                        except Exception as error:
                            exchange['error'] = str(error)

                    worker = threading.Thread(target=echo, daemon=True); worker.start()
                    try:
                        pid, handle, _, begin = spawn('pending', b'NET_PENDING_EMPTY', f'{server.getsockname()[1]} {nonce}')
                        if exchange['echoes']:
                            raise AssertionError('echo sent before the empty-queue negative control')
                        exchange['empty_reply_observed_before_echo'] = True
                        release_echo.set()
                        ready = f'NET_PENDING_READY pid={pid} first={handle} second=96'.encode()
                        guest.expect(ready, start=begin, timeout=20)
                        exchange['retained_datagram_bytes'] = 32
                        exchange['nonconsuming_reply_lower_bound'] = 96
                        command(guest, f'net-revoke {pid}', b'result=0', timeout=10)
                        # Repeated replacement processes must get only their own
                        # information response, never the prior UDP payload.
                        run('info', b'NET_INFO_PASS')
                        guest.expect(b'NET_REVOKED_PASS' + f' pid={pid} '.encode(), start=begin, timeout=10)
                        wait(pid); restored(baseline); info(1, 0)
                        duration = re.search(rb'NET_REVOKED_PASS pid=' + str(pid).encode() + rb' first=(\d+)',
                                             bytes(guest.output)[begin:])
                        if not duration or int(duration[1]) >= 500_000_000:
                            raise AssertionError('queued payload was not revoked before its reply deadline')
                        exchange['revoke_before_reply_timeout_ns'] = int(duration[1])
                        if exchange['echoes'] != 1 or exchange.get('error'):
                            raise AssertionError(str(exchange))
                        exchange['status'] = 'passed'
                    finally:
                        cancel.set(); worker.join(timeout=1)
                        if worker.is_alive():
                            raise AssertionError('UDP fixture failed to stop')
            report['checks'].append('pending_data_revoke_new_pid_reuse_and_revoked_pid_reconnect_denial')

            # Guest time still enforces the 60 s contract; TCG under parallel
            # build load can take substantially longer in host wall time.
            output = run('idle', b'NET_IDLE_PASS', timeout=240)
            report['idle_timeout_ns'] = int(re.search(rb'NET_IDLE_PASS pid=\d+ first=(\d+)', output)[1])
            restored(baseline); info(1, 0); report['checks'].append('idle_60s_connection_and_resource_reclamation')

            stopped = command(guest, 'net-stop', b'kind=exited code=', timeout=60)
            if b'[net] close=0' not in stopped or b'kind=exited code=0' not in stopped:
                raise AssertionError('service reset failed')
            restored(before_service)
            previous = service
            service = start_service()
            if previous == service:
                raise AssertionError('service PID reused')
            run('info', b'NET_INFO_PASS'); info(1, 0); restored(baseline)
            report['checks'].append('orderly_reset_restart_and_precise_resource_baseline')

            pid, _, _, begin = spawn('service_lost', b'NET_SERVICE_READY')
            command(guest, f'kill {service}', b'kill: accepted', timeout=30)
            guest.expect(b'NET_SERVICE_LOST_PASS', start=begin, timeout=15); wait(pid)
            # Device contract: abrupt death without confirmed device_status=0
            # retains both 64-entry queues (2 * (4096 + 64 * 2048) = 66 pages).
            # A new owner must not obtain an instance whose DMA is unproven.
            quarantined = (before_service[0] - 66, before_service[1], before_service[2])
            for _ in range(3):
                output = command(guest, 'net-start 41', b'net: start error=-11', timeout=30)
                if b'[net-start] pid=' in output:
                    raise AssertionError('quarantined NIC acquired by a new owner')
                restored(quarantined)
            report['quarantined_dma_pages'] = 66
            report['resources_after_quarantine'] = quarantined
            report['checks'].append('service_kill_closes_peers_retains_dma_and_rejects_three_regrants')
            (out / 'guest_before_reboot.serial.log').write_bytes(guest.output)
            guest.close(); guest = None
            # The current contract permits recovery after a platform reset.
            # Validate a new boot rather than silently releasing unsafe pages.
            guest = Guest(system / 'xos-install.iso', str(out.relative_to(ROOT / 'build')) + '/reboot',
                          iso=True, network=True, work_disk=disk, qmp_enabled=not args.serial_only,
                          network_capture=out / 'reboot.pcap')
            report['reboot_qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks'); pump(guest, 0.2)
            command(guest, 'audio stop', b'audio: service stopped')
            warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
            if b'[net] close=0' not in warmup:
                raise AssertionError('reboot NIC warmup reset failed')
            restored(before_service)
            service = start_service(); run('info', b'NET_INFO_PASS'); info(1, 0); restored(baseline)
            stopped = command(guest, 'net-stop', b'kind=exited code=', timeout=60)
            if b'[net] close=0' not in stopped or b'kind=exited code=0' not in stopped:
                raise AssertionError('reboot service reset failed')
            restored(before_service)
            report['checks'].append('platform_reboot_restores_driver_and_final_precise_resources')
            verify_inputs(); report['status'] = 'passed'
    except (Exception, SystemExit) as error:
        report['status'] = 'not_run' if guest is None else 'failed'; report['error'] = str(error)
        raise
    finally:
        if guest:
            (out / 'guest.serial.log').write_bytes(guest.output); guest.close()
        report['evidence_files'] = {path.name: sha(path) for path in out.iterdir() if path.is_file()}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS N2 lifecycle guest: {len(report["checks"])} checks, {args.revoke_rounds} revocations')


if __name__ == '__main__':
    main()
