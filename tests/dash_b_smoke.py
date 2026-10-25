# SPDX-License-Identifier: Apache-2.0
"""Guest acceptance for dash B0 delegation, B1 scripts, and sbase tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re
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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--dash-manifest', type=Path, required=True)
    parser.add_argument('--sbase-manifest', type=Path, required=True)
    parser.add_argument('--seed-manifest', type=Path, default=ROOT/'build/cpp_bundle/seed_manifest.json')
    parser.add_argument('--sysroot-manifest', type=Path, default=ROOT/'build/cpp_bundle/sysroot_manifest.json')
    parser.add_argument('--release-images', type=Path,
                        help='use the SHA256-pinned 1024 release work disk instead of Seed/sysroot manifests')
    parser.add_argument('--report', type=Path, default=ROOT/'build/dash_b_acceptance_report.json')
    args = parser.parse_args()
    system = json.loads((args.system/'manifest.json').read_text())
    dash = json.loads(args.dash_manifest.read_text())
    sbase = json.loads(args.sbase_manifest.read_text())
    report = {'status': 'failed', 'system_build_id': system['build_id'],
              'xos_sha256': sha(args.system/'xos.img'), 'dash_sha256': dash['sha256'],
              'sbase_commit': sbase['commit'], 'checks': [], 'commands': [],
              'fixtures': {}, 'configuration': {
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
        with tempfile.TemporaryDirectory(prefix='xos_dash_b_') as folder_name:
            folder = Path(folder_name)
            disk = folder/'work.img'
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
            for directory in ('/tests', '/src', '/out', '/tmp'):
                ensure_directory(disk, directory)
            transfer(disk, 'import', '/usr/bin/dash', dash_elf)
            for name, item in sbase['tools'].items():
                binary = ROOT/item['path']
                if sha(binary) != item['sha256']:
                    raise AssertionError('sbase tool mismatch: '+name)
                transfer(disk, 'import', item['guest_path'], binary)
            fixtures = ROOT/'tests/fixtures/dash_b'
            for source in sorted(fixtures.iterdir()):
                if not source.is_file():
                    continue
                target = ('/tests/' if source.suffix == '.sh' else '/src/') + source.name
                transfer(disk, 'import', target, source)
                report['fixtures'][source.name] = sha(source)
            # The build script replaces this file after the intentional failure.
            transfer(disk, 'import', '/src/current.c', fixtures/'bad.c')

            guest = Guest(args.system/'xos.img', 'dash_b', work_disk=disk)
            report['qemu_command'] = guest.command
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            pump(guest, 1.5)
            baseline = resources(guest)
            report['baseline_resources'] = baseline

            def run(line, code, markers=(), timeout=240):
                output = command(guest, line, f'kind=exited code={code}'.encode(), timeout=timeout)
                for marker in markers:
                    if marker not in output:
                        raise AssertionError(f'{line}: missing {marker!r}: {output[-4000:]!r}')
                current = resources(guest)
                if current != baseline:
                    raise AssertionError(f'{line}: resources {current} != {baseline}')
                report['commands'].append({'line': line, 'exit_code': code,
                    'resources': current, 'output_tail': output[-4000:].decode(errors='replace')})
                return output

            run('exec-driver /usr/bin/x86_64-elf-gcc --version', 0, (b'GCC',), 90)
            report['checks'].append('legacy_direct_driver_grant')

            denied = run('exec-driver /usr/bin/dash /tests/unauthorized.sh', 126,
                         (b'Not owner',), 90)
            if b'kind=exited code=0' in denied:
                raise AssertionError('unauthorized nested driver unexpectedly ran')
            missing = command(guest, 'stat /out/unauthorized.o', b'error=', timeout=30)
            if re.search(rb'size=', missing):
                raise AssertionError('unauthorized compiler produced an object')
            report['checks'].append('unprivileged_delegation_rejected_without_side_effect')

            output = run('dash /tests/build.sh', 0,
                         (b'case=c', b'parameter=fallback', b'expected_compile_failure=',
                          b'c_app=42', b'case=cpp', b'cpp_app=toolchain',
                          b'sbase_tools=ok', b'dash_b1=ok'), 360)
            if b'unexpected_compile_success' in output:
                raise AssertionError('negative compile unexpectedly succeeded')
            report['checks'] += [
                'bounded_dash_to_gcc_cc1_as_ld_delegation',
                'bounded_dash_to_gxx_cc1plus_as_ld_delegation',
                'case_function_dot_and_parameter_expansion',
                'compile_failure_copy_modify_retry_and_execute',
                'sbase_cat_cp_mkdir_mv_rm_guest_tools',
            ]
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
