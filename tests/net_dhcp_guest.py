#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify sealed DHCP lifecycle in real QEMU against an independent wire peer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from make_work_disk import create_fat32
from net_dhcp_peer import DhcpPeer
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xos_app import tree_receipt
CASES = ('renew', 'expire', 'nak_config_change', 'rebind_new_issuer', 'malformed',
         'acd_conflict', 'conflict_backoff_recover', 'service_restart')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(system, fixtures):
    manifest = json.loads((system / 'manifest.json').read_text())
    receipt = json.loads((fixtures / 'receipt.json').read_text())
    network = json.loads((system / 'net_lwip_inputs.json').read_text())
    expected = json.loads((ROOT / 'tests/fixtures/network/dhcp_profile.json').read_text())
    profile = network.get('dhcp_profile', {})
    if {key: value for key, value in profile.items() if key != 'source_sha256'} != expected:
        raise ValueError('system is not the explicit sealed DHCP fixture profile')
    if network.get('static_profile') or network.get('dns_probe'):
        raise ValueError('DHCP fixture cannot have a static fallback/probe profile')
    for name, value in manifest['sources'].items():
        if digest(ROOT / name) != value:
            raise ValueError('changed system source: ' + name)
    for name, value in manifest['artifacts'].items():
        if digest(system / name) != value['sha256']:
            raise ValueError('changed system artifact: ' + name)
    for name, value in receipt['sources'].items():
        if digest(ROOT / name) != value:
            raise ValueError('changed fixture source: ' + name)
    if receipt['sdk_tree_sha256'] != tree_receipt(system / 'sdk')[0] or receipt['libc_linked']:
        raise ValueError('fixture SDK mismatch')
    if receipt['artifacts']['net_dhcp_probe.elf'] != digest(fixtures / 'net_dhcp_probe.elf'):
        raise ValueError('fixture binary mismatch')
    return {'build_id': manifest['build_id'], 'manifest_sha256': digest(system / 'manifest.json'),
            'sdk_tree_sha256': receipt['sdk_tree_sha256'], 'network_profile': profile,
            'image_sha256': digest(system / 'xos-install.iso'), 'probe_sha256': digest(fixtures / 'net_dhcp_probe.elf')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--scenarios', nargs='+', choices=CASES, default=CASES)
    args = parser.parse_args()
    system, fixtures, out = (value.resolve() for value in (args.system, args.fixtures, args.output))
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': digest(Path(__file__)),
              'peer_sha256': digest(ROOT / 'tests/net_dhcp_peer.py'), 'scenarios': []}
    guest = peer = None
    try:
        report.update(validate(system, fixtures))
        with tempfile.TemporaryDirectory(prefix='xos_dhcp_guest_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512); transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/dhcp.elf', fixtures / 'net_dhcp_probe.elf')
            peer = DhcpPeer()
            guest = Guest(system / 'xos-install.iso', 'dhcp', iso=True, work_disk=disk, network=True,
                          qmp_enabled=False, network_peer_port=peer.port,
                          network_capture=out / 'network.pcap', log_dir=out)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            guest.expect(b'[net] ready native_v2=1', timeout=60)
            command(guest, 'demo quiet', b'demo tasks'); command(guest, 'audio stop', b'audio: service stopped')
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)

            def start_service():
                start = len(guest.output)
                text = command(guest, 'net-start 41', b'[net-start] pid=', timeout=30)
                pid = int(re.search(rb'\[net-start\] pid=(\d+)', text)[1])
                guest.expect(b'[net] ready native_v2=1', start=start, timeout=30)
                return pid

            def launch(mode, service, nonce):
                start = len(guest.output)
                text = command(guest, f'spawn-file /bin/dhcp.elf {mode} {service} {nonce}', b'[loader] started pid=', timeout=30)
                pid = int(re.search(rb'\[loader\] started pid=(\d+)', text)[1])
                return pid, start

            def finish(pid, start, mode, timeout=80):
                command(guest, f'wait {pid}', b'kind=exited code=0', timeout=timeout)
                text = bytes(guest.output[start:])
                if f'DHCP_GUEST_PASS {mode}'.encode() not in text or b'DHCP_GUEST_FAIL' in text:
                    raise AssertionError('native DHCP probe failed: ' + text.decode(errors='replace'))
                if peer.error:
                    raise AssertionError(peer.error)
                return text

            # Warm executable/FAT caches before taking strict process/device
            # resource baselines. The warmup is separately recorded.
            nonce = peer.arm('bound'); service = start_service()
            pid, start = launch('bound', service, nonce); finish(pid, start, 'bound')
            report['warmup'] = peer.finish_scenario()
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            baseline = resources(guest); report['resources_before'] = baseline
            for case in args.scenarios:
                mode = 'restart_old' if case == 'service_restart' else case
                nonce = peer.arm(mode); service = start_service()
                pid, start = launch(mode, service, nonce)
                if case == 'service_restart':
                    guest.expect(b'DHCP_GUEST_RESTART_READY', start=start, timeout=35)
                    command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
                    old_report = peer.finish_scenario()
                    nonce = peer.arm('bound'); replacement = start_service()
                    if replacement == service:
                        raise AssertionError('restart reused process identity')
                    finish(pid, start, 'restart_old', timeout=30)
                    new_pid, new_start = launch('bound', replacement, nonce)
                    text = finish(new_pid, new_start, 'bound', timeout=40)
                    item = {'scenario': case, 'old_service': service, 'new_service': replacement,
                            'old': old_report, 'new': peer.finish_scenario()}
                    if item['old']['dhcp'][0]['xid'] == item['new']['dhcp'][0]['xid']:
                        raise AssertionError('restart reused discovery XID')
                else:
                    text = finish(pid, start, mode)
                    item = peer.finish_scenario()
                    for value in item['udp']:
                        if ('DHCP_GUEST_CHALLENGE data=' + value['challenge']).encode() not in text:
                            raise AssertionError('guest omitted independent fresh UDP challenge')
                    if case in ('expire', 'nak_config_change') and b'DHCP_GUEST_OLD_RESOURCES_CLOSED' not in text:
                        raise AssertionError('old socket/DNS ticket retirement not verified')
                    item['native_snapshots'] = [line.decode() for line in text.splitlines() if line.startswith((b'DHCP_GUEST_BOUND ', b'DHCP_GUEST_FINAL '))]
                command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
                item['resources_after'] = resources(guest)
                if item['resources_after'] != baseline:
                    raise AssertionError('service/process/device resource imbalance: ' + str(item))
                item['status'] = 'passed'; report['scenarios'].append(item)
            report['resources_after'] = resources(guest)
        peer.close(); peer = None
        guest.close(); guest = None
        if validate(system, fixtures)['manifest_sha256'] != report['manifest_sha256']:
            raise ValueError('qualification inputs changed')
        report.update(status='passed_subset', capture_sha256=digest(out / 'network.pcap'),
                      serial_sha256=digest(out / 'dhcp_serial.log'))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if peer is not None:
            report['peer_error'] = peer.error
            report['peer_reports'] = peer.reports
            peer.close()
        if guest is not None:
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('DHCP_REAL_GUEST_SCENARIOS_PASSED=' + str(len(report['scenarios'])))

if __name__ == '__main__':
    main()
