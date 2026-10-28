# SPDX-License-Identifier: Apache-2.0
"""Exercise the reboot admission gate with a synthetic persistent marker."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes, pump
from xypm_format import canonical, require, sha_file
from xypm_image import Disk


def build_probe(sdk, output):
    compiler = shutil.which('x86_64-elf-gcc')
    libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
    subprocess.run([compiler, '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
                    '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '-fno-use-cxa-atexit',
                    '-idirafter', str(sdk/'include'), '-nostdlib', '-static', '-no-pie',
                    '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T', str(sdk/'user.ld'),
                    str(sdk/'crt0.o'), str(ROOT/'tests/fixtures/package_p2/persistent_gate_probe.cpp'),
                    '-Wl,--start-group', str(sdk/'lib/libxos.a'), libgcc, '-Wl,--end-group', '-o', str(output)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); system = args.system.resolve(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((system/'manifest.json').read_text()); image = system/'xos.img'
    require(sha_file(image) == manifest['artifacts']['xos.img']['sha256'], 'system image mismatch')
    probe = out/'gate_probe.elf'; build_probe(system/'sdk', probe)
    report = {'status': 'failed', 'system_build_id': manifest['build_id'], 'image_sha256': sha_file(image),
              'probe_sha256': sha_file(probe), 'test_sha256': sha_file(Path(__file__)), 'checks': [],
              'not_run': ['actual_package_journal', 'package_recovery', 'power_loss']}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p2_gate_') as temp:
            folder = Path(temp); disk = folder/'work.img'; create_fat32(disk, 512)
            with Disk(disk, folder) as backend:
                for name in ('/var', '/var/lib', '/var/lib/xypm', '/var/lib/xypm/transaction', '/out'):
                    backend.command('mkdir', name)
                backend.command('import', '/out/gate_probe', probe)
                sentinel = folder/'sentinel'; sentinel.write_bytes(b'preserved')
                backend.command('import', '/out/sentinel', sentinel)
            boot = folder/'boot.img'; shutil.copyfile(image, boot)
            def start(work_disk=disk):
                g = Guest(boot, 'package_p2_persistent_gate', work_disk=work_disk)
                g.expect(b'xos64> ', timeout=40); send_bytes(g, b'run\r')
                g.expect_supervisor(trace=True, timeout=40); pump(g, 1.5)
                return g
            guest = start(); baseline = resources(guest); report['baseline'] = baseline
            def command(line, expected):
                begin = len(guest.output); send_bytes(guest, line.encode()+b'\r')
                guest.expect(expected, start=begin, timeout=60); guest.expect_supervisor(start=begin, timeout=60)
                data = bytes(guest.output)[begin:]; require(b'GATE_FAIL' not in data, 'probe failure: '+repr(data))
                require(resources(guest) == baseline, 'resource drift after '+line)
            command('exec-file /out/gate_probe normal', b'command blocked')
            command('mkdir /out/blocked', b'command blocked')
            command('cat /out/sentinel', b'preserved')
            report['checks'].append('boot_marker_blocks_process_and_writes_but_allows_reads')
            command('maint-recover /out/gate_probe keep', b'persistent recovery is required')
            command('exec-file /out/gate_probe normal', b'command blocked')
            report['checks'].append('successful_worker_cannot_unlock_while_marker_remains')
            guest.close(); (out/'retained_boot.log').write_bytes(guest.output); guest = None
            with Disk(disk, folder, True) as backend:
                require(backend.info('/var/lib/xypm/transaction') is not None, 'marker lost before recovery')
                require(backend.info('/hello.elf') is None, 'bootstrap wrote before recovery')
                require(backend.info('/out/blocked') is None, 'blocked mutation escaped')
            guest = start(); baseline = resources(guest)
            command('exec-file /out/gate_probe normal', b'command blocked')
            report['checks'].append('marker_survives_reboot_and_prevents_bootstrap_writes')
            command('maint-recover /out/gate_probe clear', b'maintenance: completed')
            command('exec-file /out/gate_probe normal', b'GATE_NORMAL')
            report['checks'].append('cleared_marker_allows_guard_release')
            guest.close(); (out/'first_boot.log').write_bytes(guest.output); guest = None
            with Disk(disk, folder, True) as backend:
                require(backend.info('/var/lib/xypm/transaction') is None, 'marker survived clear')
                require(backend.info('/out/blocked') is None, 'blocked mutation escaped')
                require(backend.export('/out/sentinel').read_bytes() == b'preserved', 'sentinel changed')
            guest = start(); baseline = resources(guest)
            command('exec-file /out/gate_probe normal', b'GATE_NORMAL')
            report['checks'].append('normal_start_after_clean_restart')
            command('maint-run /out/gate_probe mark', b'maintenance: retained')
            command('exec-file /out/gate_probe normal', b'command blocked')
            command('maint-recover /out/gate_probe clear', b'maintenance: completed')
            command('exec-file /out/gate_probe normal', b'GATE_NORMAL')
            report['checks'].append('worker_created_marker_retains_guard_until_cleared')
            guest.close(); (out/'clean_boot.log').write_bytes(guest.output); guest = None
            bad_disk = folder/'bad_work.img'; create_fat32(bad_disk, 512)
            with bad_disk.open('r+b') as stream:
                stream.write(bytes(512))
            guest = start(bad_disk); baseline = resources(guest)
            command('exec-file /out/gate_probe normal', b'command blocked')
            command('maint-recover /out/missing', b'error=')
            command('exec-file /out/gate_probe normal', b'command blocked')
            report['checks'].append('unreadable_disk_fails_closed')
            report['status'] = 'passed'
    except Exception as exc:
        report['error'] = str(exc)
        if guest: report['output_tail'] = bytes(guest.output[-6000:]).decode(errors='replace')
        raise
    finally:
        if guest:
            guest.close(); (out/'last_boot.log').write_bytes(guest.output)
        (out/'gate_report.json').write_bytes(canonical(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
