#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real Net2, two controlled DNS endpoints, one deadline and epoch retirement."""
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
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from net_dns_probe_guest import captured_dns_queries, wire_name
from net_tcp_window_peer import TcpWindowPeer, checksum, GUEST_IP, GUEST_MAC, HOST_MAC
from process_smoke import command, resources
from task_smoke import send_bytes
from toolchain import tool
from work_disk import transfer
from xos_app import tree_receipt

SERVERS = [socket.inet_aton(value) for value in ('10.0.2.2', '10.0.2.3')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MultiResolverPeer(TcpWindowPeer):
    def __init__(self):
        self.queries = []
        self.cache_answers = {}
        self.addresses = [f'192.0.2.{value}' for value in secrets.SystemRandom().sample(range(1, 255), 3)]
        self.cancelled_query = None
        self.late_cancel_sent = False
        self.late_cancel_reply = None
        self.late_cancel_port_unreachable = 0
        super().__init__()

    def answer(self, server, port, query, address, ttl):
        txid = struct.unpack('!H', query[:2])[0]
        record = struct.pack('!HHHIH4s', 0xc00c, 1, 1, ttl, 4, socket.inet_aton(address))
        payload = struct.pack('!HHHHHH', txid, 0x8180, 1, 1, 0, 0) + query[12:] + record
        udp = struct.pack('!HHHH', 53, port, len(payload) + 8, 0)
        pseudo = server + GUEST_IP + struct.pack('!BBH', 0, 17, len(udp) + len(payload))
        udp = udp[:6] + struct.pack('!H', checksum(pseudo + udp + payload) or 0xffff)
        ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 28 + len(payload), 0, 0, 64, 17, 0, server, GUEST_IP)
        ip = ip[:10] + struct.pack('!H', checksum(ip)) + ip[12:]
        packet = ip + udp + payload
        self._emit(0x0800, packet)
        return packet

    def release_cancelled(self):
        with self.lock:
            if self.cancelled_query is None or self.late_cancel_sent:
                raise AssertionError('cancel barrier has no unique original query')
            server, port, query = self.cancelled_query
            self.late_cancel_reply = self.answer(server, port, query, '192.0.2.254', 120)
            self.late_cancel_sent = True

    def _receive(self, frame):
        kind = frame[12:14]
        if kind == b'\x08\x06':
            if len(frame) < 42:
                raise ValueError('truncated ARP')
            arp = frame[14:42]
            if arp[:8] == bytes.fromhex('0001080006040001') and arp[24:28] in SERVERS:
                self._emit(0x0806, bytes.fromhex('0001080006040002') + HOST_MAC + arp[24:28] + arp[8:18])
            return
        if kind != b'\x08\x00':
            return
        ip = frame[14:]
        size = (ip[0] & 15) * 4 if ip else 0
        total = struct.unpack('!H', ip[2:4])[0] if len(ip) >= 20 else 0
        if (size < 20 or not size <= total <= len(ip) or checksum(ip[:size]) or
                ip[12:16] != GUEST_IP or ip[16:20] not in SERVERS):
            raise ValueError('invalid resolver IPv4 envelope')
        if ip[9] == 1:
            # Cancellation removes the last UDP PCB. A delayed DNS answer may
            # therefore elicit the ordinary ICMP port-unreachable response.
            # Accept only the exact quoted injected answer, not arbitrary ICMP.
            icmp = ip[size:total]
            with self.lock:
                if (not self.late_cancel_sent or self.late_cancel_reply is None or
                        len(icmp) != 36 or icmp[:2] != b'\x03\x03' or checksum(icmp) or
                        icmp[8:] != self.late_cancel_reply[:28]):
                    raise ValueError('unexpected ICMP resolver response')
                self.late_cancel_port_unreachable += 1
            return
        if ip[9] != 17:
            raise ValueError('unexpected resolver protocol')
        udp = ip[size:total]
        pseudo = GUEST_IP + ip[16:20] + struct.pack('!BBH', 0, 17, len(udp))
        if len(udp) < 20 or checksum(pseudo + udp):
            raise ValueError('invalid resolver UDP checksum')
        port, target, length, _ = struct.unpack('!HHHH', udp[:8])
        if target != 53 or port < 1024 or length != len(udp):
            raise ValueError('invalid resolver UDP endpoint')
        query = udp[8:]
        txid, flags, questions, answers, authority, additional = struct.unpack('!HHHHHH', query[:12])
        if (flags, questions, answers, authority, additional) != (0x100, 1, 0, 0, 0) or query[-4:] != b'\0\1\0\1':
            raise ValueError('invalid IN A question')
        encoded = query[12:-4]
        server = ip[16:20]
        names = ('cache', 'deadline', 'cancel', 'quota', 'hold0', 'hold1', 'hold2', 'hold3', 'replacement')
        name = next((name for name in names if encoded == wire_name(name + '.p1i.test')), None)
        if name is None:
            raise ValueError('unexpected resolver name')
        with self.lock:
            self.queries.append({'name': name, 'resolver': socket.inet_ntoa(server), 'source_port': port,
                                 'transaction_id': txid, 'monotonic_seconds': time.monotonic()})
            if name == 'cancel' and self.cancelled_query is None:
                self.cancelled_query = server, port, query
            if name != 'cache' or server != SERVERS[1]:
                return
            key = port, txid
            if key not in self.cache_answers:
                index = len(self.cache_answers)
                if index >= len(self.addresses):
                    raise ValueError('unexpected cache miss')
                self.cache_answers[key] = index
            index = self.cache_answers[key]
            self.answer(server, port, query, self.addresses[index], 2 if index == 0 else 120)


def spawn(guest, arguments):
    first = len(guest.output)
    result = command(guest, 'spawn-file /bin/p1i.elf ' + arguments, b'[loader] started pid=', timeout=35)
    return int(re.search(rb'\[loader\] started pid=(\d+)', result)[1]), first


def exercise(guest, peer, report):
    guest.expect(b'xos64> ', timeout=45)
    send_bytes(guest, b'run\r')
    guest.expect_supervisor(trace=True, timeout=45)
    command(guest, 'demo quiet', b'demo tasks')
    command(guest, 'audio stop', b'audio: service stopped')
    command(guest, 'net-stop', b'kind=exited code=0', timeout=45)
    command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=45)
    report['resources_before'] = resources(guest)
    first = len(guest.output)
    result = command(guest, 'net-start 41', b'[net-start] pid=', timeout=45)
    service = int(re.search(rb'\[net-start\] pid=(\d+)', result)[1])
    guest.expect(b'[net] ready native_v2=1', start=first, timeout=45)
    process, first = spawn(guest, f'cache {service}')
    guest.expect(b'P1I_AWAIT_EPOCH', start=first, timeout=55)
    command(guest, 'net-dns-configure off', b'[net-dns-config] epoch=2')
    command(guest, 'net-dns-configure on', b'[net-dns-config] epoch=3')
    command(guest, f'wait {process}', b'kind=exited code=0', timeout=30)
    if b'P1I_CACHE_PASS' not in guest.output[first:] or len(peer.cache_answers) != 3:
        raise AssertionError('cache/epoch probe did not finish')
    process, first = spawn(guest, f'deadline {service}')
    guest.expect(b'P1I_CANCELLED', start=first, timeout=20)
    peer.release_cancelled()
    command(guest, f'wait {process}', b'kind=exited code=0', timeout=10)
    if b'P1I_DEADLINE_CANCEL_PASS' not in guest.output[first:]:
        raise AssertionError('deadline/cancellation probe did not finish')
    owners = []
    for index in range(4):
        process, first = spawn(guest, f'hold {service} hold{index}.p1i.test')
        guest.expect(b'P1I_HOLD ticket=', start=first, timeout=10)
        guest.expect(b'\n', start=guest.output.index(b'P1I_HOLD ticket=', first), timeout=5)
        ticket = int(re.search(rb'P1I_HOLD ticket=(\d+)\n', guest.output[first:])[1])
        owners.append({'pid': process, 'ticket': ticket})
        if index == 0:
            result = command(guest, f'exec-file /bin/p1i.elf foreign {service} {ticket}',
                             b'P1I_FOREIGN_PASS', timeout=10)
            if b'kind=exited code=0' not in result:
                raise AssertionError('foreign ticket probe failed')
    result = command(guest, f'exec-file /bin/p1i.elf full {service}', b'P1I_GLOBAL_QUOTA_PASS', timeout=10)
    if b'kind=exited code=0' not in result:
        raise AssertionError('global quota probe failed')
    command(guest, f'kill {owners[0]["pid"]}', b'kill: accepted')
    command(guest, f'wait {owners[0]["pid"]}', b'kind=killed')
    replacement, first = spawn(guest, f'hold {service} replacement.p1i.test')
    guest.expect(b'P1I_HOLD ticket=', start=first, timeout=10)
    for process in [item['pid'] for item in owners[1:]] + [replacement]:
        command(guest, f'kill {process}', b'kill: accepted')
        command(guest, f'wait {process}', b'kind=killed')
    command(guest, 'net-stop', b'[net] close=0', timeout=45)
    report['resources_after'] = resources(guest)
    if report['resources_before'] != report['resources_after']:
        raise AssertionError('network service resource recovery mismatch')
    report.update(service=service, quota_owners=owners, replacement_pid=replacement, epochs=[1, 2, 3])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    system, output = args.system.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': sha(Path(__file__)), 'physical_nic': 'not_run'}
    guest = peer = None
    try:
        manifest = json.loads((system / 'manifest.json').read_text())
        if manifest['sources'] != system_sources():
            raise ValueError('system sources changed')
        for name, entry in manifest['artifacts'].items():
            if sha(system / name) != entry['sha256']:
                raise ValueError('system artifact changed: ' + name)
        profile = json.loads((system / 'net_lwip_inputs.json').read_text())['static_profile']
        if profile.get('revision') != 3 or profile.get('resolvers') != ['10.0.2.2', '10.0.2.3']:
            raise ValueError('two ordered resolver profile required')
        sdk = system / 'sdk'
        binary = output / 'net_multi_resolver_probe.elf'
        source = ROOT / 'tests/fixtures/network/net_multi_resolver_probe.cpp'
        command_line = [tool('g++'), '-std=c++17', '-Os', '-Wall', '-Wextra', '-Werror',
                        '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-stack-protector',
                        '-fno-pie', '-fno-pic', '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++',
                        '-ffunction-sections', '-fdata-sections', '-I', str(sdk / 'include'), str(source),
                        '-nostdlib', '-static', '-no-pie',
                        '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                        '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), str(sdk / 'lib/libxos.a'), '-o', str(binary)]
        subprocess.run(command_line, check=True)
        report.update(build_id=manifest['build_id'], system_manifest_sha256=sha(system / 'manifest.json'),
                      sdk_tree_sha256=tree_receipt(sdk)[0], source_sha256=sha(source), elf_sha256=sha(binary),
                      compile_command=command_line, profile=profile)
        with tempfile.TemporaryDirectory(prefix='xos_p1i_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin'); transfer(disk, 'import', '/bin/p1i.elf', binary)
            peer = MultiResolverPeer()
            capture = output / 'network.pcap'
            guest = Guest(system / 'xos-install.iso', 'p1i_resolver', work_disk=disk, network=True,
                          network_peer_port=peer.port, network_capture=capture, log_dir=output, qmp_enabled=False)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            exercise(guest, peer, report)
            peer.close()
            guest.close(); guest = None
            if peer.error:
                raise AssertionError(peer.error)
            report.update(queries=peer.queries, answers=peer.addresses, late_cancel_sent=peer.late_cancel_sent,
                          late_cancel_port_unreachable=peer.late_cancel_port_unreachable)
            for address in ('10.0.2.2', '10.0.2.3'):
                count = captured_dns_queries(capture, address)
                if count != sum(item['resolver'] == address for item in peer.queries):
                    raise AssertionError('pcap differs from observed resolver destination')
            for name in ('cache', 'deadline'):
                if {item['resolver'] for item in peer.queries if item['name'] == name} != {'10.0.2.2', '10.0.2.3'}:
                    raise AssertionError('failover did not visit both authorized resolvers: ' + name)
            if manifest['sources'] != system_sources():
                raise AssertionError('source changed while guest was running')
            report.update(capture_sha256=sha(capture), serial_sha256=sha(output / 'p1i_resolver_serial.log'),
                          status='passed_multiple_resolver_subset')
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if peer is not None:
            peer.close()
        if guest is not None:
            guest.close()
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
