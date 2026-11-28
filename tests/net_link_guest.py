#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual VirtIO link loss, fresh DHCP/ACD and controlled PCI removal attempt."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from glibc_static_guest import system_sources
from make_work_disk import create_fat32
from net_dhcp_peer import DhcpPeer, IP1, IP2, SERVER1, SERVER2, HOST_MAC, GUEST_MAC
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LinkPeer(DhcpPeer):
    def __init__(self):
        self.link_evidence = {'arp': [], 'application': [], 'late_arp_injected': None}
        super().__init__()

    def _receive(self, frame):
        if self.mode is not None and len(frame) >= 42:
            if frame[12:14] == b'\x08\x06':
                arp = frame[14:42]
                if arp[:8] == bytes.fromhex('0001080006040001'):
                    self.link_evidence['arp'].append({'source': socket.inet_ntoa(arp[14:18]),
                        'target': socket.inet_ntoa(arp[24:28]), 'time': time.monotonic()})
                    if arp[24:28] == SERVER2:
                        return  # Hold the old UDP payload and SYN behind real ARP.
            elif frame[12:14] == b'\x08\x00':
                ip = frame[14:]
                if ip[12:16] in (IP1, IP2) and ip[16:20] in (SERVER1, SERVER2):
                    self.link_evidence['application'].append({'source': socket.inet_ntoa(ip[12:16]),
                        'target': socket.inet_ntoa(ip[16:20]), 'protocol': ip[9], 'time': time.monotonic()})
                    if ip[16:20] == SERVER2:
                        raise ValueError('old ARP-queued UDP/TCP resurrected after link loss')
        super()._receive(frame)

    def prepare_new_lease(self):
        with self.lock:
            self.address = IP2
            self.link_evidence['lease_replacement_time'] = time.monotonic()

    def inject_old_arp(self):
        with self.lock:
            self._emit(0x806, bytes.fromhex('0001080006040002') + HOST_MAC + SERVER2 + GUEST_MAC + self.address)
            self.link_evidence['late_arp_injected'] = time.monotonic()


def has_device(tree, identity):
    if isinstance(tree, dict):
        return tree.get('qdev_id') == identity or any(has_device(value, identity) for value in tree.values())
    if isinstance(tree, list):
        return any(has_device(value, identity) for value in tree)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixtures', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system, fixture, out = (item.resolve() for item in (args.system, args.fixtures, args.output))
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': sha(Path(__file__)), 'physical_nic': 'not_run',
              'automatic_unannounced_device_rebind': 'unsupported_no_presence_generation_or_PCI_hotplug_manager'}
    guest = peer = None
    try:
        manifest = json.loads((system / 'manifest.json').read_text())
        if manifest['sources'] != system_sources():
            raise ValueError('system source mismatch')
        for name, entry in manifest['artifacts'].items():
            if sha(system / name) != entry['sha256']:
                raise ValueError('system artifact mismatch: ' + name)
        receipt = json.loads((fixture / 'receipt.json').read_text())
        if any(sha(ROOT / name) != value for name, value in receipt['sources'].items()):
            raise ValueError('fixture source mismatch')
        if receipt['sdk_tree_sha256'] != tree_receipt(system / 'sdk')[0] or receipt['libc_linked']:
            raise ValueError('native SDK mismatch')
        for name, value in receipt['artifacts'].items():
            if sha(fixture / name) != value:
                raise ValueError('fixture artifact mismatch')
        profile = json.loads((system / 'net_lwip_inputs.json').read_text())['dhcp_profile']
        expected = json.loads((ROOT / 'tests/fixtures/network/link_profile.json').read_text())
        if {name: value for name, value in profile.items() if name != 'source_sha256'} != expected:
            raise ValueError('sealed link qualification profile mismatch')
        report.update(build_id=manifest['build_id'], system_manifest_sha256=sha(system / 'manifest.json'),
                      fixture_receipt_sha256=sha(fixture / 'receipt.json'), sdk_tree_sha256=receipt['sdk_tree_sha256'],
                      image_sha256=sha(system / 'xos-install.iso'), profile=profile)
        with tempfile.TemporaryDirectory(prefix='xos_link_guest_') as folder:
            disk = Path(folder) / 'work.img'
            create_fat32(disk, 512); transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/dhcp.elf', fixture / 'net_dhcp_probe.elf')
            peer = LinkPeer()
            guest = Guest(system / 'xos-install.iso', 'net_link', work_disk=disk, network=True,
                          network_peer_port=peer.port, network_device_id='xosnet0',
                          network_capture=out / 'network.pcap', log_dir=out, qtest_enabled=True)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            command(guest, 'net-probe 41', b'NET_USER_DRIVER_PASS', timeout=60)
            report['resources_before'] = resources(guest)
            nonce = peer.arm('link_loss')
            first = len(guest.output)
            text = command(guest, 'net-start 41', b'[net-start] pid=', timeout=30)
            service = int(re.search(rb'\[net-start\] pid=(\d+)', text)[1])
            guest.expect(b'[net] ready native_v2=1', start=first, timeout=30)
            begin = len(guest.output)
            text = command(guest, f'spawn-file /bin/dhcp.elf link_loss {service} {nonce}', b'[loader] started pid=', timeout=30)
            child = int(re.search(rb'\[loader\] started pid=(\d+)', text)[1])
            guest.expect(b'DHCP_LINK_READY_QUEUED', start=begin, timeout=45)
            if not any(item['target'] == '10.0.2.3' for item in peer.link_evidence['arp']):
                raise AssertionError('old transport did not actually wait for ARP')
            report['link_down_qmp'] = guest.qmp('set_link', {'name': 'xosnet0', 'up': False})
            guest.expect(b'DHCP_LINK_DOWN_READY', start=begin, timeout=15)
            before = len(peer.report['dhcp'])
            pump(guest, 3)
            if len(peer.report['dhcp']) != before:
                raise AssertionError('DHCP continued while link was down')
            peer.prepare_new_lease()
            report['link_up_qmp'] = guest.qmp('set_link', {'name': 'xosnet0', 'up': True})
            guest.expect(b'DHCP_LINK_UP_BOUND', start=begin, timeout=20)
            peer.inject_old_arp()
            command(guest, f'wait {child}', b'kind=exited code=0', timeout=15)
            if b'DHCP_GUEST_PASS link_loss' not in guest.output[begin:]:
                raise AssertionError('link epoch probe did not finish')
            scenario = peer.finish_scenario()
            for address in ('10.0.2.15', '10.0.2.16'):
                if sum(item['source'] == '0.0.0.0' and item['target'] == address for item in peer.link_evidence['arp']) < 3:
                    raise AssertionError('fresh address lacked three actual ACD probes: ' + address)
            discoveries = [item['xid'] for item in scenario['dhcp'] if item['type'] == 1]
            if len(set(discoveries)) < 2 or len(scenario['udp']) != 2:
                raise AssertionError('link up did not perform a new DHCP transaction and challenge')
            report.update(link_status='passed_actual_link_loss_reacquisition', wire=scenario,
                          link_evidence=peer.link_evidence)
            command(guest, 'net-stop', b'kind=exited code=0', timeout=60)
            report['resources_after'] = resources(guest)
            if report['resources_before'] != report['resources_after']:
                raise AssertionError('link lifecycle resource recovery mismatch')
            # Device removal is a separate real operation, after the controller
            # has stopped/waited the service and released DMA/MMIO authority.
            device = {'scope': 'host-forced removal; host prepares new PCI resources; controller grants a fresh service'}
            report['device_reappearance'] = device
            old_nonce = peer.arm('device_old')
            first = len(guest.output)
            text = command(guest, 'net-start 41', b'[net-start] pid=', timeout=30)
            old_service = int(re.search(rb'\[net-start\] pid=(\d+)', text)[1])
            guest.expect(b'[net] ready native_v2=1', start=first, timeout=30)
            first = len(guest.output)
            text = command(guest, f'spawn-file /bin/dhcp.elf device_old {old_service} {old_nonce}', b'[loader] started pid=', timeout=30)
            old_client = int(re.search(rb'\[loader\] started pid=(\d+)', text)[1])
            guest.expect(b'DHCP_DEVICE_READY_QUEUED', start=first, timeout=30)
            device['old_wire'] = peer.finish_scenario()
            command(guest, 'net-stop', b'kind=exited code=0', timeout=30)
            guest.expect(b'DHCP_DEVICE_OLD_CLOSED', start=first, timeout=15)
            device['old_service_pid'] = old_service
            device['pci_before'] = guest.qmp('query-pci')
            # qtest is used only while vCPUs are stopped, after old authority
            # has been retired. Capture config registers, never old MMIO.
            def config_read(offset):
                guest.qtest(f'outl 0xcf8 {0x80002800 + offset:#x}')
                return int(guest.qtest('inl 0xcfc'), 16)

            def config_write(offset, value):
                guest.qtest(f'outl 0xcf8 {0x80002800 + offset:#x}')
                guest.qtest(f'outl 0xcfc {value:#x}')

            guest.qmp('stop')
            saved = {offset: config_read(offset) for offset in (0, 4, 16, 20, 24, 28, 32, 36, 60)}
            guest.qmp('cont')
            if saved[0] != 0x10411af4 or saved[4] & 6 or saved[60] & 255 != 10:
                raise AssertionError('old PCI function is not quiescent with the expected exclusive resources')
            device['old_config_after_stop'] = saved
            if not has_device(device['pci_before'], 'xosnet0'):
                raise AssertionError('named physical PCI function not found')
            device['delete_result'] = guest.qmp('device_del', {'id': 'xosnet0'})
            for _ in range(10):
                pump(guest, 0.1)
                device['pci_after_delete'] = guest.qmp('query-pci')
                if not has_device(device['pci_after_delete'], 'xosnet0'):
                    break
            if has_device(device['pci_after_delete'], 'xosnet0'):
                device['ACPI_eject'] = 'not_acknowledged'
                path = '/machine/peripheral/xosnet0'
                device['realized_before'] = guest.qmp('qom-get', {'path': path, 'property': 'realized'})
                device['host_unrealize'] = guest.qmp('qom-set', {'path': path, 'property': 'realized', 'value': False})
                device['pci_after_unrealize'] = guest.qmp('query-pci')
                if has_device(device['pci_after_unrealize'], 'xosnet0'):
                    raise AssertionError('host unrealize did not actually remove the old PCI function')
            else:
                device['ACPI_eject'] = 'acknowledged'
            device['add_result'] = guest.qmp('device_add', {'driver': 'virtio-net-pci', 'id': 'xosnet1',
                'netdev': 'xosnet', 'addr': '05.0', 'disable-legacy': 'on', 'romfile': '', 'mac': '52:54:00:12:34:56'})
            device['pci_after_add'] = guest.qmp('query-pci')
            if not has_device(device['pci_after_add'], 'xosnet1'):
                raise AssertionError('replacement did not appear in PCI enumeration')
            failed = command(guest, 'net-start 41', b'xsh> ', timeout=20)
            if b'net: start error=-7' not in failed or b'[net-start] pid=' in failed:
                raise AssertionError('unconfigured replacement did not fail closed')
            device['unconfigured_start'] = failed.decode(errors='replace')
            guest.qmp('stop')
            config_write(4, 0x400)  # Decode and bus mastering remain disabled.
            for offset in (16, 20, 24, 28, 32, 36):
                config_write(offset, saved[offset])
            route = config_read(60)
            config_write(60, (route & ~255) | (saved[60] & 255))
            device['new_config_before_grant'] = {offset: config_read(offset) for offset in saved}
            guest.qmp('cont')
            nonce = peer.arm('bound')
            first = len(guest.output)
            text = command(guest, 'net-start 41', b'[net-start] pid=', timeout=30)
            replacement = int(re.search(rb'\[net-start\] pid=(\d+)', text)[1])
            if replacement == old_service:
                raise AssertionError('replacement reused old service identity')
            guest.expect(b'[net] ready native_v2=1', start=first, timeout=30)
            command(guest, f'wait {old_client}', b'kind=exited code=0', timeout=15)
            if b'DHCP_GUEST_PASS device_old_identity' not in guest.output:
                raise AssertionError('old caller did not reject replacement identity')
            text = command(guest, f'exec-file /bin/dhcp.elf bound {replacement} {nonce}', b'kind=exited code=0', timeout=40)
            if b'DHCP_GUEST_PASS bound' not in text:
                raise AssertionError('replacement did not acquire a fresh lease and complete its challenge')
            peer.inject_old_arp()
            pump(guest, 0.5)
            device['new_wire'] = peer.finish_scenario()
            if len(device['new_wire']['arp_probes']) < 3:
                raise AssertionError('replacement omitted fresh ACD')
            old_xids = {item['xid'] for item in device['old_wire']['dhcp'] if item['type'] == 1}
            new_xids = {item['xid'] for item in device['new_wire']['dhcp'] if item['type'] == 1}
            if not new_xids or old_xids & new_xids:
                raise AssertionError('replacement reused an old DHCP acquisition')
            device['new_service_pid'] = replacement
            device['pci_after_grant'] = guest.qmp('query-pci')
            command(guest, 'net-stop', b'kind=exited code=0', timeout=30)
            device['resources_after'] = resources(guest)
            if device['resources_after'] != report['resources_before']:
                raise AssertionError('controlled reappearance did not recover the resource baseline')
            device['status'] = 'passed_controlled_reappearance_with_host_prepared_PCI_resources'
            if manifest['sources'] != system_sources():
                raise AssertionError('source changed during qualification')
            report['status'] = 'passed_link_and_controlled_reappearance_subset'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if peer is not None:
            report['peer_error'] = peer.error
            peer.close()
        if guest is not None:
            guest.close()
        for name in ('network.pcap', 'net_link_serial.log'):
            if (out / name).exists():
                report[name + '_sha256'] = sha(out / name)
        (out / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
