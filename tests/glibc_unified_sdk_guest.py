# SPDX-License-Identifier: Apache-2.0
"""Run detached SDK C and C++ consumers with Xsh and same-SDK dash on one work disk."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from dash_glibc_preview_guest import bind_preview
from glibc_static_guest import build_newlib_parent
from make_work_disk import create_fat32
from package_p2_verify_guest import quiet_maintenance_guest
from process_smoke import command, resources
from shell_launch_support import bind_system
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import canonical, load_json, require, sha_file, verify_package
from xypm_sdk_profile import verify_profile

CPP = (b'GLIBC_UNIFIED_GLOBAL_CTOR', b'GLIBC_UNIFIED_CXX_THREADS_TLS_UNWIND_STACK_PASS',
       b'GLIBC_UNIFIED_MAIN_TLS_DTOR')
PATH = (b'GLIBC_CWD_ACCESS_PASS',)


def bound_program(consumer, name, binary, profile, binding, sources):
    project = consumer / name
    receipt_path = project / 'build/build_receipt.json'
    receipt = load_json(receipt_path)
    for key in ('profile_sha256', 'sdk_manifest_sha256', 'sdk_tree_sha256'):
        require(receipt[key] == binding[key], 'application receipt binding differs: ' + key)
    for path, original in sources.items():
        require(receipt['inputs'][path] == sha_file(ROOT / original), 'application source differs: ' + path)
    elf = project / 'build' / (binary + '.elf')
    require(sha_file(elf) == receipt['output_sha256'], 'linked application differs from receipt')
    package = verify_package(consumer / (name + '.xpk'), profile)
    manifest = package['manifest']
    entry = next(item for item in manifest['files'] if item['path'] == 'usr/bin/' + binary)
    require(entry['role'] == 'executable' and entry['sha256'] == sha_file(elf), 'XPK executable differs')
    require(manifest['build_receipt']['sha256'] == sha_file(receipt_path), 'XPK build receipt differs')
    return elf, {'elf_sha256': sha_file(elf), 'xpk_sha256': package['sha256'],
                 'receipt_sha256': sha_file(receipt_path),
                 'sources_sha256': {original: receipt['inputs'][path] for path, original in sources.items()}}


def run(args, report):
    system = args.system.resolve(strict=True)
    iso = system / 'xos-install.iso'
    out = args.output.resolve()
    kit = args.kit.resolve(strict=True)
    profile_path = kit / 'profile.json'
    sdk = kit / 'sdk'
    profile = load_json(profile_path)
    binding = verify_profile(profile, 'glibc', sdk) | {'sdk_manifest_sha256': sha_file(sdk / 'manifest.json')}
    report['sdk'] = binding
    system_info = bind_system(system)
    report['system_build_id'] = system_info['build_id']
    report['system_manifest_sha256'] = sha_file(system / 'manifest.json')
    report['iso_sha256'] = sha_file(iso)
    report['dash'] = bind_preview(SimpleNamespace(preview_receipt=args.dash_receipt, glibc_sdk=sdk,
                                                  glibc_profile=profile_path))
    dash = ROOT / load_json(args.dash_receipt)['elf']

    sources = {'src/main.cpp': 'tests/fixtures/glibc_g3/unified_cpp_probe.cpp'}
    for name in ('xos_stack_bounds.cpp', 'xos_stack_bounds.hpp'):
        sources['src/' + name] = 'src/ports/webkit/threading/' + name
    cpp, cpp_info = bound_program(args.consumer, 'cxx', 'unified_cxx', profile, binding, sources)
    path, path_info = bound_program(args.consumer, 'path', 'g3_cwd', profile, binding,
                                   {'src/main.c': 'tests/fixtures/glibc_g3/cwd_probe.c'})
    report['programs'] = {'cxx': cpp_info, 'cwd': path_info}
    xypm_build = load_json(args.xypm_receipt)
    xypm = Path(xypm_build['elf'])
    package = verify_package(Path(xypm_build['package']), profile)
    entry = next(item for item in package['manifest']['files'] if item['path'] == 'usr/bin/xypm')
    require(package['sha256'] == xypm_build['sha256'] and entry['sha256'] == sha_file(xypm),
            'xypm build and XPK differ')
    report['programs']['xypm'] = {'xpk_sha256': package['sha256'], 'elf_sha256': sha_file(xypm)}
    setup_report = {'system_build_id': report['system_build_id'], 'elfs': {}}
    setup = build_newlib_parent(system, out, setup_report, 'glibc_g3/cwd_setup.c', 'g3_cwd_setup')
    report['fat_setup'] = {'elf_sha256': sha_file(setup), 'libc': 'system_newlib'}

    disk = out / 'work.img'
    create_fat32(disk, 512)
    for folder in ('/bin', '/g3_cwd', '/g3_cwd/sub', '/g3_cwd/路'):
        transfer(disk, 'mkdir', folder)
    data = out / 'data.txt'
    data.write_text('path access fixture\n')
    for name in ('plain.txt', 'read-only.txt'):
        transfer(disk, 'import', '/g3_cwd/' + name, data)
    files = {'unified_cxx': cpp, 'g3_cwd': path, 'g3_cwd_setup': setup, 'dash_glibc': dash, 'xypm': xypm}
    for name, elf in files.items():
        transfer(disk, 'import', '/bin/' + name, elf)
    shell = out / 'apps.sh'
    shell.write_text("set -e\n/bin/unified_cxx\ncd /g3_cwd/sub\n/bin/g3_cwd /g3_cwd/sub\n"
                     "value=$(printf '%s' unified)\ntest \"$value\" = unified\n"
                     "printf 'GLIBC_UNIFIED_DASH_PASS\\n'\n")
    transfer(disk, 'import', '/bin/apps.sh', shell)
    report['script_sha256'] = sha_file(shell)

    guest = Guest(iso, 'glibc_unified_sdk', work_disk=disk, iso=True, qmp_enabled=False, log_dir=out)
    try:
        report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        guest.expect(b'xos64> ', timeout=60)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=60)
        quiet_maintenance_guest(guest)
        baseline = resources(guest)
        report['baseline'] = baseline

        def check(label, line, markers):
            output = command(guest, line, b'kind=exited code=', timeout=120)
            position = 0
            for marker in markers:
                position = output.find(marker, position)
                require(position >= 0, label + ' missing ordered output: ' + repr(output[-3000:]))
                position += len(marker)
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
            require(exits == [b'0'] and resources(guest) == baseline, label + ' exit or resource mismatch')
            report['runs'].append(label)

        check('fat_setup', 'exec-file /bin/g3_cwd_setup', (b'GLIBC_CWD_READONLY_READY',))
        check('stock_xypm', 'exec-file /bin/xypm --version', (b'xypm 0.4.0 (P3 offline repositories)',))
        for _ in range(3):
            check('xsh_cxx', 'exec-file /bin/unified_cxx', CPP)
            check('xsh_cwd', 'exec-file /bin/g3_cwd /', PATH)
            check('dash_combination', '/bin/dash_glibc /bin/apps.sh',
                  CPP + PATH + (b'GLIBC_UNIFIED_DASH_PASS',))
    finally:
        guest.close()
    report['fat_readback'] = {}
    for name, elf in files.items():
        copy = out / (name + '.fat')
        transfer(disk, 'export', '/bin/' + name, copy)
        require(sha_file(elf) == sha_file(copy), 'FAT application differs: ' + name)
        report['fat_readback'][name] = sha_file(copy)
    report['disk_sha256'] = sha_file(disk)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'kit', 'consumer', 'dash-receipt', 'xypm-receipt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runs': [], 'test_sha256': sha_file(__file__)}
    try:
        run(args, report)
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.output / 'report.json').write_bytes(canonical(report))


if __name__ == '__main__':
    main()
