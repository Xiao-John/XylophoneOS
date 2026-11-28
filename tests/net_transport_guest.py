#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fresh HTTP/UDP byte challenges through the native N2 service, with pinned PID."""
import argparse
from collections import Counter
import hashlib
import json
import re
import secrets
import socket
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt
from build_net_transport_probe import INPUTS
from net_tcp_window_peer import TcpWindowPeer

RESPONSE_LABELS = {
    'http': 'NET2_HTTP status=201 bytes=32',
    'udp': 'NET2_UDP bytes=32',
    'tcp_close': 'NET2_TCP bytes=32',
    'tcp_half': 'NET2_HALF_CLOSE bytes=32',
}


def response_record(kind, nonce, challenge_hex):
    return f'{RESPONSE_LABELS[kind]} nonce={nonce} data={challenge_hex}'.encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--serial-only', action='store_true', help='disable unused QMP socket')
    parser.add_argument('--dash', type=Path)
    parser.add_argument('--dash-sha256')
    args = parser.parse_args()
    system, payload, out = args.system.resolve(), args.payload.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'not_run', 'runner_sha256': sha(Path(__file__)), 'checks': [], 'exchanges': [],
              'not_run': ['NIC_reset_failure_quarantine', 'packet_loss_reordering', 'DNS_DHCP_TLS'],
              'lifecycle_runner': 'tests/net_service_guest.py'}
    if not args.dash:
        report['not_run'].append('dash_shell')
    guest, window_peer = None, None

    def restored(expected):
        for _ in range(20):
            actual = resources(guest)
            if actual == expected:
                return
            pump(guest, 0.1)
        raise AssertionError(f'resource mismatch: {actual} expected {expected}')

    def start_service():
        begin = len(guest.output)
        output = command(guest, 'net-start 41', b'[net-start] pid=', timeout=60)
        match = re.search(rb'\[net-start\] pid=(\d+)', output)
        if not match:
            raise AssertionError('service PID missing')
        guest.expect(b'[net] ready native_v2=1', start=begin, timeout=60)
        return int(match[1])

    def exchange(kind, pid, baseline, shell='xsh'):
        nonce, challenge = secrets.token_hex(16), secrets.token_bytes(32)
        address_family = socket.SOCK_DGRAM if kind == 'udp' else socket.SOCK_STREAM
        host = {'kind': kind, 'shell': shell, 'nonce': nonce, 'challenge_sha256': hashlib.sha256(challenge).hexdigest()}
        with socket.socket(socket.AF_INET, address_family) as server:
            server.bind(('127.0.0.1', 0)); server.settimeout(1)
            port = server.getsockname()[1]
            if kind != 'udp':
                server.listen(1)
            cancel = threading.Event()
            active, active_lock = [], threading.Lock()
            report['exchanges'].append(host)
            def wait_for(operation):
                for _ in range(45):
                    if cancel.is_set():
                        raise RuntimeError('fixture cancelled')
                    try:
                        return operation()
                    except socket.timeout:
                        pass
                raise TimeoutError('host fixture deadline')
            def serve():
                try:
                    if kind == 'udp':
                        data, peer = wait_for(lambda: server.recvfrom(2048))
                        if data != nonce.encode():
                            raise ValueError('UDP request nonce mismatch')
                        host['request_sha256'] = hashlib.sha256(data).hexdigest()
                        server.sendto(challenge, peer)
                    else:
                        connection, _ = wait_for(server.accept)
                        with active_lock:
                            if cancel.is_set():
                                connection.close()
                                raise RuntimeError('fixture cancelled after accept')
                            active.append(connection)
                        with connection:
                            connection.settimeout(20); data = b''
                            if kind in ('tcp_close', 'tcp_half'):
                                while len(data) < 32:
                                    part = connection.recv(32 - len(data))
                                    if not part:
                                        raise ValueError('TCP nonce truncated')
                                    data += part
                                if data != nonce.encode():
                                    raise ValueError('TCP request nonce mismatch')
                                if kind == 'tcp_half':
                                    if connection.recv(1) != b'':
                                        raise ValueError('half-close did not deliver FIN after nonce')
                                    host['client_eof_before_response'] = True
                                    host['request_sha256'] = hashlib.sha256(data).hexdigest()
                                    connection.sendall(challenge)
                                    connection.shutdown(socket.SHUT_WR)
                                    host['verified_half_close'] = True
                                    return
                                connection.sendall(challenge)
                                queued = b''
                                while True:
                                    part = connection.recv(2048)
                                    if not part:
                                        break
                                    queued += part
                                    if len(queued) > 8192:
                                        raise ValueError('TCP queued bytes exceeded expected length')
                                if queued != nonce.encode() * 256:
                                    raise ValueError('TCP accepted bytes lost or reordered at close')
                                host['client_eof'] = True
                                host['queued_tx_bytes_verified'] = len(queued)
                                host['request_sha256'] = hashlib.sha256(data + queued).hexdigest()
                                return
                            while b'\r\n\r\n' not in data and len(data) <= 16384:
                                part = connection.recv(1024)
                                if not part:
                                    break
                                data += part
                            if (not data.startswith(f'GET /{nonce} HTTP/1.1\r\n'.encode()) or
                                    f'Host: 10.0.2.2:{port}\r\n'.encode() not in data or
                                    b'Connection: close\r\n' not in data or not data.endswith(b'\r\n\r\n')):
                                raise ValueError('HTTP request/nonce mismatch')
                            host['request_sha256'] = hashlib.sha256(data).hexdigest()
                            response = b'HTTP/1.1 201 Created\r\nContent-Length: 32\r\nConnection: close\r\n\r\n' + challenge
                            connection.sendall(response[:17]); connection.sendall(response[17:])
                            connection.shutdown(socket.SHUT_WR)
                            host['client_eof'] = connection.recv(1) == b''
                            if not host['client_eof']:
                                raise ValueError('HTTP client did not close')
                except Exception as error:
                    host['error'] = str(error)
            worker = threading.Thread(target=serve, daemon=True); worker.start()
            try:
                prefix = 'exec-file /bin/netprobe.elf' if shell == 'xsh' else '/bin/dash /tests/netprobe.sh'
                output = command(guest, f'{prefix} {kind} {pid} {port} {nonce}', b'kind=exited code=', timeout=90)
                expected = response_record(kind, nonce, challenge.hex())
                if (output.splitlines().count(expected) != 1 or b'NET2_GUEST_PASS' not in output or
                        b'kind=exited code=0' not in output):
                    raise AssertionError(output[-4000:])
                worker.join(timeout=25)
                if worker.is_alive() or host.get('error'):
                    raise AssertionError(str(host))
            except (Exception, SystemExit) as error:
                host['guest_error'] = str(error)
                raise
            finally:
                cancel.set()
                with active_lock:
                    for connection in active:
                        try:
                            connection.shutdown(socket.SHUT_RDWR)
                        except OSError:
                            pass
                        connection.close()
                server.close()
                worker.join(timeout=2)
                host['worker_stopped'] = not worker.is_alive()
        restored(baseline)
        host['verified_bytes'] = 32
        report['checks'].append(f'{shell}_{kind}_fresh_exact_bytes_and_resources')

    def concurrent_exchanges(pid, baseline):
        # Every peer first receives its independent nonce, then all four peers
        # release the replies together. Thus four live application sessions
        # coexist before any guest can finish its exchange.
        barrier = threading.Barrier(4, timeout=20)
        cancel = threading.Event()
        sockets, workers, connections = [], [], []
        connection_lock = threading.Lock()
        states = []

        def serve(server, state, challenge):
            try:
                if state['kind'] == 'udp':
                    data, peer = server.recvfrom(2048)
                    if data != state['nonce'].encode():
                        raise ValueError('concurrent UDP nonce mismatch')
                    state['request_sha256'] = hashlib.sha256(data).hexdigest()
                    barrier.wait(); server.sendto(challenge, peer)
                else:
                    connection, _ = server.accept()
                    with connection_lock:
                        connections.append(connection)
                    with connection:
                        connection.settimeout(20); data = b''
                        while b'\r\n\r\n' not in data and len(data) <= 16384:
                            part = connection.recv(1024)
                            if not part:
                                break
                            data += part
                        expected = f'GET /{state["nonce"]} HTTP/1.1\r\n'.encode()
                        if not data.startswith(expected) or not data.endswith(b'\r\n\r\n'):
                            raise ValueError('concurrent HTTP request mismatch')
                        state['request_sha256'] = hashlib.sha256(data).hexdigest()
                        barrier.wait()
                        connection.sendall(b'HTTP/1.1 201 Created\r\nContent-Length: 32\r\nConnection: close\r\n\r\n' + challenge)
                        connection.shutdown(socket.SHUT_WR)
                        if connection.recv(1) != b'':
                            raise ValueError('concurrent HTTP close mismatch')
                        state['client_eof'] = True
                state['verified_bytes'] = 32
            except Exception as error:
                if not cancel.is_set():
                    state['error'] = str(error)
                barrier.abort()

        begin = len(guest.output)
        try:
            for kind in ('http', 'udp', 'http', 'udp'):
                nonce, challenge = secrets.token_hex(16), secrets.token_bytes(32)
                server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM if kind == 'udp' else socket.SOCK_STREAM)
                sockets.append(server); server.bind(('127.0.0.1', 0)); server.settimeout(25)
                if kind == 'http':
                    server.listen(1)
                state = {'kind': kind, 'shell': 'xsh', 'concurrent': True, 'nonce': nonce,
                         'challenge_sha256': hashlib.sha256(challenge).hexdigest(), 'expected_hex': challenge.hex()}
                states.append(state); report['exchanges'].append(state)
                worker = threading.Thread(target=serve, args=(server, state, challenge), daemon=True)
                workers.append(worker); worker.start()
                output = command(guest, f'spawn-file /bin/netprobe.elf {kind} {pid} {server.getsockname()[1]} {nonce}',
                                 b'[loader] started pid=', timeout=20)
                match = re.search(rb'\[loader\] started pid=(\d+)', output)
                if not match:
                    raise AssertionError('missing concurrent application PID')
                state['pid'] = int(match[1])
            for state in states:
                output = command(guest, f'wait {state["pid"]}', b'[wait]', timeout=45)
                if f'[wait] pid={state["pid"]} kind=exited code=0'.encode() not in output:
                    raise AssertionError(repr(output[-3000:]))
            for worker in workers:
                worker.join(timeout=25)
            output = bytes(guest.output)[begin:]
            if output.count(b'NET2_GUEST_PASS') != 4:
                raise AssertionError('four concurrent applications did not complete successfully')
            expected_records = []
            for state, worker in zip(states, workers):
                if worker.is_alive() or state.get('error'):
                    raise AssertionError(str(state))
                expected_records.append(response_record(state['kind'], state['nonce'], state.pop('expected_hex')))
            received_records = [line for line in output.splitlines() if line.startswith((b'NET2_HTTP ', b'NET2_UDP '))]
            if Counter(received_records) != Counter(expected_records):
                raise AssertionError('concurrent response records did not match their requesting applications')
            restored(baseline)
            report['checks'].append('four_concurrent_applications_distinct_http_udp_challenges_and_resources')
        finally:
            cancel.set(); barrier.abort()
            with connection_lock:
                for connection in connections:
                    try:
                        connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    connection.close()
            for server in sockets:
                server.close()
            for worker in workers:
                worker.join(timeout=2)

    try:
        manifest = json.loads((system / 'manifest.json').read_text())
        receipt_path = payload.with_name('net_transport_probe.receipt.json')
        receipt = json.loads(receipt_path.read_text())
        if (receipt['binary_sha256'] != sha(payload) or receipt['sdk_tree_sha256'] != tree_receipt(system / 'sdk')[0] or
                receipt['sources'] != {name: sha(ROOT / name) for name in INPUTS} or receipt['libc_linked']):
            raise ValueError('probe build inputs differ from matching source/SDK')
        for name, digest in manifest['sources'].items():
            if sha(ROOT / name) != digest:
                raise ValueError('system source mismatch: ' + name)
        for name, entry in manifest['artifacts'].items():
            if sha(system / name) != entry['sha256']:
                raise ValueError('system artifact mismatch: ' + name)
        if 'net_lwip_inputs.json' not in manifest['artifacts']:
            raise ValueError('rebuild system with XOS_LWIP_SOURCE_ARCHIVE enabled')
        if args.dash and (not args.dash_sha256 or sha(args.dash) != args.dash_sha256):
            parser.error('--dash requires its matching --dash-sha256')
        report.update(build_id=manifest['build_id'], image_sha256=sha(system / 'xos-install.iso'),
                      payload_sha256=sha(payload), receipt_sha256=sha(receipt_path),
                      sdk_tree_sha256=receipt['sdk_tree_sha256'], lwip_inputs_sha256=sha(system / 'net_lwip_inputs.json'))
        if args.dash:
            report['dash_sha256'] = args.dash_sha256
        with tempfile.TemporaryDirectory(prefix='xos_net2_guest_') as temporary:
            folder = Path(temporary); disk = folder / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin'); transfer(disk, 'mkdir', '/tests')
            transfer(disk, 'import', '/bin/netprobe.elf', payload)
            if args.dash:
                transfer(disk, 'import', '/bin/dash', args.dash)
                script = folder / 'netprobe.sh'; script.write_text('/bin/netprobe.elf "$@"\nstatus=$?\nexit "$status"\n')
                transfer(disk, 'import', '/tests/netprobe.sh', script)
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
            pid = start_service(); baseline = resources(guest)
            report['service_pid'] = pid
            for shell in (['xsh', 'dash'] if args.dash else ['xsh']):
                exchange('http', pid, baseline, shell); exchange('udp', pid, baseline, shell)
                exchange('tcp_close', pid, baseline, shell)
                exchange('tcp_half', pid, baseline, shell)
            concurrent_exchanges(pid, baseline)
            nonce = secrets.token_hex(16)
            output = command(guest, f'exec-file /bin/netprobe.elf http {pid + 1} 9 {nonce}',
                             b'kind=exited code=1', timeout=45)
            if b'NET2_FAIL error=-202' not in output:
                raise AssertionError('wrong service PID accepted')
            restored(baseline); report['checks'].append('wrong_service_pid_denied')
            with socket.socket() as unused:
                unused.bind(('127.0.0.1', 0)); closed_port = unused.getsockname()[1]
                output = command(guest, f'exec-file /bin/netprobe.elf http {pid} {closed_port} {nonce}',
                                 b'kind=exited code=1', timeout=45)
                if b'NET2_FAIL error=' not in output:
                    raise AssertionError('closed port produced success')
            restored(baseline); report['checks'].append('closed_port_fails_and_reclaims')
            stopped = command(guest, 'net-stop', b'kind=exited code=', timeout=60)
            if b'[net] close=0' not in stopped or b'kind=exited code=0' not in stopped:
                raise AssertionError('service reset/close failure')
            restored(before_service)
            replacement = start_service()
            if replacement == pid:
                raise AssertionError('service PID unexpectedly reused')
            exchange('http', replacement, resources(guest))
            exchange('tcp_half', replacement, resources(guest))
            stopped = command(guest, 'net-stop', b'kind=exited code=', timeout=60)
            if b'[net] close=0' not in stopped or b'kind=exited code=0' not in stopped:
                raise AssertionError('replacement reset/close failure')
            restored(before_service); report['checks'].append('service_restart_and_resource_baseline')
            # A second NIC backend gives the private peer direct control of
            # TCP receive windows. The ordinary user-network exchanges above
            # remain a separate host-socket compatibility regression.
            (out / 'user_network.serial.log').write_bytes(guest.output)
            guest.close(); guest = None
            window_peer = TcpWindowPeer()
            report['window_peer_sha256'] = sha(ROOT / 'tests/net_tcp_window_peer.py')
            report['controlled_closes'] = []
            guest = Guest(system / 'xos-install.iso', str(out.relative_to(ROOT / 'build')) + '/window_guest',
                          iso=True, network=True, work_disk=disk, qmp_enabled=not args.serial_only,
                          network_capture=out / 'window_network.pcap', network_peer_port=window_peer.port)
            report['window_qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks'); pump(guest, 0.2)
            command(guest, 'audio stop', b'audio: service stopped')
            warmup = command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
            if b'[net] close=0' not in warmup:
                raise AssertionError('packet NIC warmup reset failed')
            before_service = resources(guest)
            pid = start_service(); baseline = resources(guest)
            for shell in (['xsh', 'dash'] if args.dash else ['xsh']):
                for mode in ('queued', 'drained'):
                    nonce, challenge = secrets.token_hex(16), secrets.token_bytes(32)
                    port, state = window_peer.begin(mode, nonce, challenge, shell)
                    report['controlled_closes'].append(state)
                    prefix = 'exec-file /bin/netprobe.elf' if shell == 'xsh' else '/bin/dash /tests/netprobe.sh'
                    output = command(guest, f'{prefix} tcp_{mode} {pid} {port} {nonce}', b'kind=exited code=', timeout=90)
                    expected = response_record('tcp_close', nonce, challenge.hex())
                    accepted = 4096 if mode == 'queued' else 8192
                    marker = f'NET2_TCP_{mode.upper()}_CLOSE accepted={accepted}'.encode()
                    if (output.splitlines().count(expected) != 1 or marker not in output or b'NET2_GUEST_PASS' not in output or
                            b'kind=exited code=0' not in output):
                        raise AssertionError(output[-4000:])
                    window_peer.finish(port)
                    restored(baseline)
                    report['checks'].append(f'{shell}_tcp_{mode}_controlled_window_close_and_resources')
            stopped = command(guest, 'net-stop', b'kind=exited code=', timeout=60)
            if b'[net] close=0' not in stopped or b'kind=exited code=0' not in stopped:
                raise AssertionError('packet service reset/close failure')
            restored(before_service)
            if window_peer.error:
                raise AssertionError(window_peer.error)
            report['status'] = 'passed'
    except (Exception, SystemExit) as error:
        report['status'] = 'not_run' if guest is None else 'failed'
        report['error'] = str(error)
        raise
    finally:
        if window_peer:
            try:
                window_peer.close()
            except Exception as error:
                report['status'], report['cleanup_error'] = 'failed', str(error)
            if window_peer.error:
                report['status'], report['window_peer_error'] = 'failed', window_peer.error
        if guest:
            (out / 'guest.serial.log').write_bytes(guest.output); guest.close()
        report['evidence_files'] = {path.name: sha(path) for path in out.iterdir() if path.is_file()}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] != 'passed':
        raise AssertionError(report.get('window_peer_error', report.get('cleanup_error', 'transport qualification failed')))
    print('PASS native service HTTP/UDP fresh challenge guest')


if __name__ == '__main__':
    main()
