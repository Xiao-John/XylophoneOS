# SPDX-License-Identifier: Apache-2.0
"""Guest acceptance for dash B2 redirection, shared open descriptions, and cancel."""
import argparse
import hashlib
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
from work_disk import transfer
from gcc_seed_smoke import import_manifest_files
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from released_test_disk import ARCHIVE_SHA256, prepare_release_disk, ensure_directory, sha256


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_probe(source, output, sdk):
    compiler = shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc'
    libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
    subprocess.run([
        compiler, '-B'+str(ROOT/'build/target_tools')+'/', '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
        '-idirafter', str(sdk/'include'), '-nostdlib', '-static', '-no-pie',
        '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
        '-T', str(sdk/'user.ld'), str(sdk/'crt0_posix.o'), str(source),
        '-Wl,--start-group', str(sdk/'lib/libxos.a'), str(sdk/'lib/libxos_loader.a'),
        str(sdk/'lib/libc.a'), str(sdk/'lib/libm.a'), libgcc, '-Wl,--end-group',
        '-o', str(output),
    ], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--dash-manifest', type=Path, required=True)
    parser.add_argument('--sbase-manifest', type=Path, required=True)
    parser.add_argument('--seed-manifest', type=Path, default=ROOT/'build/cpp_bundle/seed_manifest.json')
    parser.add_argument('--sysroot-manifest', type=Path, default=ROOT/'build/cpp_bundle/sysroot_manifest.json')
    parser.add_argument('--release-images', type=Path,
                        help='use the SHA256-pinned 1024 release work disk instead of Seed/sysroot manifests')
    parser.add_argument('--report', type=Path, default=ROOT/'build/dash_b2_acceptance_report.json')
    args = parser.parse_args()
    system = json.loads((args.system/'manifest.json').read_text())
    dash = json.loads(args.dash_manifest.read_text())
    sbase = json.loads(args.sbase_manifest.read_text())
    report = {'status': 'failed', 'system_build_id': system['build_id'],
              'xos_sha256': sha(args.system/'xos.img'), 'dash_sha256': dash['sha256'],
              'checks': [], 'fixtures': {}, 'configuration': {
                  'system': str(args.system.resolve()),
                  'dash_manifest': str(args.dash_manifest.resolve()),
                  'dash_manifest_sha256': sha256(args.dash_manifest),
                  'sbase_manifest': str(args.sbase_manifest.resolve()),
                  'sbase_manifest_sha256': sha256(args.sbase_manifest),
                  'release_images': str(args.release_images.resolve()) if args.release_images else None,
                  'release_archive_sha256_expected': ARCHIVE_SHA256 if args.release_images else None}}
    guest = None
    try:
        if report['xos_sha256'] != system['artifacts']['xos.img']['sha256']:
            raise AssertionError('system image does not match manifest')
        dash_elf = ROOT/dash['elf']
        if sha(dash_elf) != dash['sha256']:
            raise AssertionError('dash ELF does not match manifest')
        with tempfile.TemporaryDirectory(prefix='xos_dash_b2_') as folder_name:
            folder = Path(folder_name)
            disk = folder/'work.img'
            sdk = args.system/'sdk'
            stdio_probe = folder/'stdio_probe'
            spin_probe = folder/'spin'
            build_probe(ROOT/'tests/fixtures/dash_b2/stdio_probe.c', stdio_probe, sdk)
            build_probe(ROOT/'tests/fixtures/dash_b2/spin.c', spin_probe, sdk)
            if args.release_images:
                report['disk_input'] = prepare_release_disk(args.release_images, disk)
            else:
                seed = json.loads(args.seed_manifest.read_text())
                sysroot = json.loads(args.sysroot_manifest.read_text())
                report['disk_input'] = {
                    'mode': 'manifest_import',
                    'seed_manifest': str(args.seed_manifest.resolve()),
                    'seed_manifest_sha256': sha256(args.seed_manifest),
                    'sysroot_manifest': str(args.sysroot_manifest.resolve()),
                    'sysroot_manifest_sha256': sha256(args.sysroot_manifest)}
                create_fat32(disk, 2048)
                import_manifest_files(disk, ROOT, seed['install_files'], 'Seed install')
                import_manifest_files(disk, ROOT, sysroot['files'], 'target sysroot')
            for directory in ('/tests', '/out', '/tmp'):
                ensure_directory(disk, directory)
            transfer(disk, 'import', '/usr/bin/dash', dash_elf)
            for name, item in sbase['tools'].items():
                binary = ROOT/item['path']
                if sha(binary) != item['sha256']:
                    raise AssertionError('sbase tool mismatch: '+name)
                transfer(disk, 'import', item['guest_path'], binary)
            fixtures = ROOT/'tests/fixtures/dash_b2'
            for source in sorted(fixtures.iterdir()):
                if source.is_file():
                    transfer(disk, 'import', '/tests/'+source.name, source)
                    report['fixtures'][source.name] = sha(source)
            transfer(disk, 'import', '/out/stdio_probe', stdio_probe)
            transfer(disk, 'import', '/out/spin', spin_probe)
            report['probes'] = {'stdio_probe': sha(stdio_probe), 'spin': sha(spin_probe)}

            guest = Guest(args.system/'xos.img', 'dash_b2', work_disk=disk)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            pump(guest, 1.5)
            baseline = resources(guest)
            report['baseline_resources'] = baseline

            output = command(guest, 'dash /tests/b2.sh', b'kind=exited code=0', timeout=240)
            markers = (b'order_two_start', b'order_two_end', b'restoration_marker',
                       b'expected_redirection_failure', b'log_begin', b'alpha\nbeta\n', b'log_end',
                       b'shared_begin', b'OUT\nERR\n', b'shared_end',
                       b'split_begin', b'split_end',
                       b'builtin_begin', b'inside_builtin\n', b'builtin_end', b'b2=ok')
            for marker in markers:
                if marker not in output:
                    raise AssertionError(f'missing marker {marker!r}: {output[-12000:]!r}')
            if b'unexpected_redirection_success' in output:
                raise AssertionError('failed redirection unexpectedly succeeded')
            first = output.find(b'order_two_start')
            error = output.find(b'ERR\n', first)
            last = output.find(b'order_two_end', error)
            if first < 0 or error < first or last < error:
                raise AssertionError('2>&1 before > did not preserve stderr on the console')
            if resources(guest) != baseline:
                raise AssertionError('resources changed after redirection script')
            report['checks'] += [
                'truncate_append_and_input_redirection',
                'shared_stdout_stderr_open_description',
                'ordered_duplication_differs_from_later_open',
                'builtin_redirection_restores_parent_descriptors',
                'redirection_failure_keeps_shell_and_resources',
            ]

            send_bytes(guest, b'dash -i\r')
            guest.expect(b'$ ', timeout=60)
            cancel_start = len(guest.output)
            send_bytes(guest, b'/out/spin\r')
            pump(guest, 1.0)
            send_bytes(guest, b'\x1b')
            guest.expect(b'$ ', start=cancel_start, timeout=60)
            cancelled = bytes(guest.output[cancel_start:])
            if b'cancelled_by_escape' not in cancelled:
                raise AssertionError('Escape did not cancel nested foreground task')
            recovery_start = len(guest.output)
            send_bytes(guest, b"printf 'cancel_recovered\\n'\r")
            guest.expect(b'$ ', start=recovery_start, timeout=30)
            recovered = bytes(guest.output[recovery_start:])
            if b'cancel_recovered' not in recovered:
                raise AssertionError('dash did not recover after foreground cancel')
            send_bytes(guest, b'exit\r')
            guest.expect_supervisor(timeout=60)
            pump(guest, 0.5)
            if resources(guest) != baseline:
                raise AssertionError('resources changed after foreground cancel')
            report['checks'].append('escape_cancels_nested_foreground_and_returns_to_dash')
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        if guest is not None:
            report['output_tail'] = bytes(guest.output[-16000:]).decode(errors='replace')
        raise
    finally:
        if guest is not None:
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
