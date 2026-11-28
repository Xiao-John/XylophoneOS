#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cold-boot the selected installed profile and exercise real dynamic DHCP/TLS callers."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time

repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root / 'scripts'))
from boot_smoke import Guest
from installed_dhcp_tls_peer import installed_tls_peer
from package_p2_faults import resources, sparse_copy
from process_smoke import command
from shell_launch_support import bind_system
from task_smoke import send_bytes, pump
from xypm_format import canonical, require, sha_file, verify_package
from xypm_image import DB_PATH, INDEX_PATH, Disk, query_image

main_path = '/usr/lib/xos/installed_dhcp_tls/main'


def validate(system, installed, source):
    manifest = bind_system(system, source)
    report = json.loads((installed / 'installation.json').read_bytes())
    profile = json.loads((installed / 'profile.json').read_bytes())
    require(report['status'] == 'installed_candidate_not_run', 'installation candidate is not complete')
    require(report['composition']['system_manifest_sha256'] == sha_file(system / 'manifest.json')
            and report['composition']['ordinary_iso_sha256'] == sha_file(system / 'xos-install.iso')
            and report['profile_sha256'] == sha_file(installed / 'profile.json')
            and report['installed_disk_sha256'] == sha_file(installed / 'installed.img'),
            'selected installed bytes differ from the composition receipt')
    package = verify_package(installed / 'installed_dhcp_tls.xpk', profile, report['package_sha256'])
    require(package['manifest']['id'] == report['package_id'], 'installed package identity differs')
    require({entry['path']: entry for entry in package['manifest']['files']} == report['installed_files'],
            'installation file inventory differs from the selected XPK manifest')
    require(query_image(installed / 'installed.img', profile, 'verify-installed') == report['installed'],
            'installed ownership/payload verification differs')
    return manifest, report, profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'installation', 'certificates', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--system-source', type=Path, default=repository_root)
    args = parser.parse_args()
    system, installed, certificates, out = (value.resolve() for value in
        (args.system, args.installation, args.certificates, args.output))
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'p1_k4_installed_dhcp_tls_v1', 'checks': [], 'boots': [],
              'runner_sha256': sha_file(Path(__file__)),
              'peer_sha256': sha_file(repository_root / 'tests/installed_dhcp_tls_peer.py'),
              'not_run': ['BIOS hard-disk boot', 'physical NIC', 'general Internet trust bundle',
                          'pending dynamic ABI v3', 'online dlopen', 'SMP']}
    guest = peer = None
    try:
        manifest, installation, profile = validate(system, installed, args.system_source)
        require(all(sha_file(certificates / name) == expected
                    for name, expected in installation['composition']['trust'].items()),
                'independent TLS peer fixtures differ from the installed trust selection')
        report.update(system_build_id=manifest['build_id'], installation=installation,
                      installation_receipt_sha256=sha_file(installed / 'installation.json'))
        disk = out / 'running.img'
        sparse_copy(installed / 'installed.img', disk)
        require(sha_file(disk) == installation['installed_disk_sha256'], 'cold installation copy differs')
        with Disk(disk, out, True) as files:
            report['database_before'] = {name: sha_file(files.export(name)) for name in (DB_PATH, INDEX_PATH)}

        def boot(number):
            nonlocal guest, peer
            peer = installed_tls_peer(certificates)
            record = {'boot': number, 'disk_before_sha256': sha_file(disk), 'initial_manual_network_commands': [],
                      'topology': 'ordinary_ISO_boot_with_installed_persistent_FAT'}
            report['boots'].append(record)
            guest = Guest(system / 'xos-install.iso', f'installed_k4_{number}', iso=True,
                work_disk=disk, network=True, network_peer_port=peer.port,
                network_capture=out / f'network_{number}.pcap', log_dir=out)
            record['qemu_command'] = guest.command
            record['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=60)
            require(('build=' + manifest['build_id']).encode() in guest.output, 'booted a different system')
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            guest.expect(b'[net] ready native_v2=1', timeout=60)
            service = re.search(rb'\[net-start\] pid=(\d+)', bytes(guest.output))
            require(service is not None, 'sealed automatic network bootstrap did not run')
            record['automatic_service_pid'] = int(service[1])
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'audio: service stopped')
            return int(service[1]), record

        def launch(mode, service):
            nonce = peer.begin_case(mode)
            start = len(guest.output)
            line = f'spawn-command /usr/bin/k4_dynamic_run 0 {main_path} {mode} {service} {nonce}'
            result = command(guest, line, b'[loader] started pid=', timeout=30)
            pid = int(re.search(rb'\[loader\] started pid=(\d+)', result)[1])
            return pid, start, nonce

        def finish(pid, start, mode, timeout=65):
            result = command(guest, f'wait {pid}', b'kind=', timeout=timeout)
            text = bytes(guest.output[start:])
            require(b'kind=exited code=0' in result and b'INSTALLED_TLS_FAIL' not in text
                    and ('INSTALLED_TLS_PASS mode=' + mode).encode() in text
                    and b'INSTALLED_GNU_RUNTIME_PASS' in text
                    and b'main_tls=19 pthread_create=ENOTSUP' in text
                    and re.search(rb'DYNAMIC_RUN_EXIT slot=0 generation=\d+ pid=\d+ outcome=\d+ code=0', text),
                    'installed dynamic caller failed: ' + text[-2500:].decode(errors='replace'))
            require(not peer.error, 'independent peer failed: ' + str(peer.error))
            case = peer.cases[-1]
            if mode in ('stale-pin', 'stale-pid'):
                require(not case['flows'] and sum(item['dns_queries'] for item in peer.reports) == case['dns_queries_before'],
                        'identity rejection emitted a DNS query or TCP connection')
            else:
                require(len(case['flows']) == 1 and case['flows'][0].get('application_ready')
                        and case['flows'][0].get('tls_version') == 'TLSv1.3', 'missing independent TLS evidence')
                if mode == 'expire':
                    require(case['flows'][0].get('expiry_armed_after_tls_request')
                            and b'INSTALLED_EXPIRY_ARMED' in text and b'same_session=1' in text,
                            'expiry was not armed after authenticated TLS on the same session')
                if mode in ('once', 'trust2', 'renew'):
                    deadline = time.monotonic() + 3
                    while not case['flows'][0].get('peer_close_notify') and not peer.error and time.monotonic() < deadline:
                        pump(guest, 0.05)
                    require(case['flows'][0].get('peer_close_notify'), 'TLS graceful close was not peer verified')
            return {'mode': mode, 'controller_pid': pid, 'nonce': case['nonce'],
                    'guest_output': text.decode(errors='strict'), 'resources': resources(guest)}

        def run_case(mode, service):
            pid, start, _ = launch(mode, service)
            return finish(pid, start, mode)

        def close_boot(record):
            nonlocal guest, peer
            command(guest, 'sync', b'[files] sync=ok')
            record['peer'] = peer.snapshot()
            guest.close()
            guest = None
            peer.close()
            peer = None
            record['disk_after_sha256'] = sha_file(disk)
            record['installed_payload_after'] = query_image(disk, profile, 'verify-installed')
            require(record['installed_payload_after'] == installation['installed'], 'installed package/ownership changed')
            with Disk(disk, out, True) as files:
                record['database_after'] = {name: sha_file(files.export(name)) for name in (DB_PATH, INDEX_PATH)}
                record['owned_files_after'] = {
                    name: sha_file(files.export('/' + name)) for name in installation['installed_files']}
            require(record['database_after'] == report['database_before']
                    and record['owned_files_after'] == {name: entry['sha256']
                        for name, entry in installation['installed_files'].items()},
                    'selected XPK payload bytes or exact ownership database changed')

        service, first_boot = boot(1)
        denied_baseline = resources(guest)
        command(guest, 'spawn-command', b'Usage: spawn-command <command> [args]')
        require(resources(guest) == denied_baseline, 'missing command argument allocated a child')
        nonce = peer.begin_case('once')
        denied_start = len(guest.output)
        text = command(guest, f'spawn-file /usr/bin/k4_dynamic_run 0 {main_path} once {service} {nonce}',
                       b'[loader] started pid=', timeout=30)
        denied_pid = int(re.search(rb'\[loader\] started pid=(\d+)', text)[1])
        denied = command(guest, f'wait {denied_pid}', b'kind=', timeout=30)
        require(b'kind=exited code=126' in denied and b'dynamic-run: spawn error=-1' in guest.output[denied_start:]
                and not peer.cases[-1]['flows'] and resources(guest) == denied_baseline,
                'explicit spawn-file no-create authority changed or leaked resources')
        first_boot['spawn_file_denial'] = bytes(guest.output[denied_start:]).decode()
        report['checks'].append('spawn_file_keeps_no_create_authority_and_spawn_command_uses_common_inheritance')
        first_boot['cases'] = [run_case('once', service)]
        close_boot(first_boot)
        require(first_boot['peer']['dhcp_epochs'][0]['arp_probes']
                and first_boot['peer']['dhcp_epochs'][0]['acks'], 'automatic boot omitted wire DHCP/ACD')
        report['checks'].append('cold_installed_ISO_FAT_boot_automatic_DHCP_GNU_TLS_without_manual_start')

        service, second_boot = boot(2)
        cases = second_boot['cases'] = [run_case('once', service)]
        baseline = cases[-1]['resources']
        second_boot['resources_baseline'] = baseline
        cases.append(run_case('renew', service))
        require(cases[-1]['resources'] == baseline, 'renewed dynamic caller leaked resources')
        require(b'live_stream=1 same_session=1' in cases[-1]['guest_output'].encode(),
                'renewal authority was not read on the original live TLS session')
        report['checks'].append('second_cold_boot_and_same_epoch_DHCP_renew_with_live_TLS')

        cases.append(run_case('expire', service))
        require(cases[-1]['resources'] == baseline, 'expired caller leaked resources')
        peer.resume_leases()
        cases.append(run_case('once', service))
        first_epoch = int(re.search(r'INSTALLED_LEASE service=\d+ epoch=(\d+)', cases[-2]['guest_output'])[1])
        fresh_epoch = int(re.search(r'INSTALLED_LEASE service=\d+ epoch=(\d+)', cases[-1]['guest_output'])[1])
        require(fresh_epoch > first_epoch and cases[-1]['resources'] == baseline,
                'expiry recovery did not publish a fresh lease epoch with complete cleanup')
        report['checks'].append('lease_expiry_retires_pending_TLS_bounded_failure_and_fresh_epoch_recovery')

        pid, start, _ = launch('stop', service)
        guest.expect(b'INSTALLED_TLS_READY mode=stop', start=start, timeout=40)
        stopped_at = time.monotonic()
        stopped = command(guest, 'net-stop', b'kind=exited code=0', timeout=20)
        require(b'[net] close=0' in stopped, 'orderly service stop did not confirm device reset')
        cases.append(finish(pid, start, 'stop', timeout=8))
        elapsed = time.monotonic() - stopped_at
        require(elapsed < 8, 'orderly service stop did not wake the dynamic caller promptly')
        second_boot['orderly_stop_failure_seconds'] = elapsed
        stopped_baseline = cases[-1]['resources']
        require(stopped_baseline[0] > baseline[0]
                and stopped_baseline[1:] == (baseline[1] - 1, baseline[2] - 1),
                'orderly service stop did not release its task and completion')
        second_boot['resources_without_service'] = stopped_baseline
        peer.resume_leases()
        start = len(guest.output)
        result = command(guest, 'net-start 41', b'[net-start] pid=', timeout=30)
        replacement = int(re.search(rb'\[net-start\] pid=(\d+)', result)[1])
        guest.expect(b'[net] ready native_v2=1', start=start, timeout=30)
        require(replacement != service, 'restarted service reused the old PID')
        second_boot['restart'] = {'old_service': service, 'new_service': replacement}
        cases.append(run_case('stale-pid', service))
        cases.append(run_case('once', replacement))
        require(cases[-1]['resources'] == baseline, 'service restart recovery left resource debt')
        report['checks'].append('orderly_netd_stop_wakes_pending_dynamic_TLS_old_PID_denied_new_PID_recovers')

        cases.append(run_case('stale-pin', replacement))
        cases.append(run_case('trust2', replacement))
        require(cases[-1]['resources'] == baseline, 'trust generation update leaked caller resources')
        report['checks'].append('installed_trust_generation_mismatch_rejected_before_network_and_generation2_TLS_passed')

        pid, start, _ = launch('death', replacement)
        guest.expect(b'INSTALLED_TLS_READY mode=death', start=start, timeout=40)
        killed = time.monotonic()
        command(guest, f'kill {replacement}', b'kill: accepted')
        cases.append(finish(pid, start, 'death', timeout=8))
        elapsed = time.monotonic() - killed
        require(elapsed < 8, 'service death did not wake the dynamic caller promptly')
        second_boot['service_death_failure_seconds'] = elapsed
        # Existing device contract: without confirmed reset, the two 64-entry
        # DMA queues retain 66 pages. Regrant must fail UNKNOWN. Do not turn
        # this safety boundary into a forced reset or an invented recovery ABI.
        quarantined = (stopped_baseline[0] - 66, *stopped_baseline[1:])
        second_boot['quarantine_rejections'] = []
        for _ in range(3):
            rejected = command(guest, 'net-start 41', b'net: start error=-11', timeout=20)
            require(b'[net-start] pid=' not in rejected and resources(guest) == quarantined,
                    'quarantined DMA was regranted or repeated rejection leaked resources')
            second_boot['quarantine_rejections'].append(rejected.decode())
        second_boot['quarantined_dma_pages'] = 66
        second_boot['resources_final'] = resources(guest)
        report['checks'].append('netd_kill_wakes_pending_GNU_TLS_and_retains_exact_DMA_quarantine_with_three_regrants_denied')
        close_boot(second_boot)

        service, third_boot = boot(3)
        third_boot['cases'] = [run_case('once', service)]
        require(third_boot['cases'][0]['resources'] == baseline,
                'cold reboot after quarantine did not recover the same running baseline')
        close_boot(third_boot)
        require(third_boot['peer']['dhcp_epochs'][0]['arp_probes']
                and third_boot['peer']['dhcp_epochs'][0]['acks'], 'post-crash cold boot omitted fresh DHCP/ACD')
        report['checks'].append('third_cold_boot_recovers_quarantined_installation_with_automatic_DHCP_and_fresh_dynamic_TLS')
        require(sha_file(installed / 'installed.img') == installation['installed_disk_sha256'],
                'immutable installed candidate was modified by the runner')
        report['checks'].append('all_XPK_owned_payloads_and_database_unchanged_after_three_cold_boots_and_faults')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        if peer is not None:
            report['peer_error'] = peer.error
            report['partial_peer'] = {'dhcp_epochs': peer.reports, 'application_cases': peer.cases}
        raise
    finally:
        if guest is not None:
            guest.close()
        if peer is not None:
            peer.close()
        (out / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
