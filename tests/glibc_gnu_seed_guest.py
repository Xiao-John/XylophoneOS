#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cold-boot the assembled GNU Seed disk and run real native glibc C/C++ builds."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from build_glibc_program import verify_elf
from glibc_release_packages_guest import PYTHON_OK, boot, command
from package_glibc_release import IMAGES, INSTALLER, KIT, ORDINARY, verify_assembled, verify_disk
from package_glibc_gnu_seed import SEED_RECEIPT
from prepare_glibc_gnu_seed import install
from shell_launch_support import check_result
from task_smoke import pump
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import require_stdio_marker
from package_p2_faults import resources, sparse_copy

FIXTURES = ROOT / 'tests/fixtures'
MAKE = 'gmake -B -r -f /src/native/project.mk all'
GCC = 'x86_64-elf-gcc --sysroot=/sysroot'
GXX = 'x86_64-elf-g++ --sysroot=/sysroot'


def fixture_files():
    files = {}
    for name in ('project.h', 'project_value.c', 'project_cpp.cpp', 'project_cpp_value.cpp', 'link_error.c'):
        files['/src/native/' + name] = FIXTURES / 'shell_launch' / name
    for name in ('project_c.c', 'project.mk', 'build.sh'):
        files['/src/native/' + name] = FIXTURES / 'glibc_gnu_seed' / name
    return files


def run(args):
    receipts = args.seed_dir / 'seed_receipt.json'
    receipt = load_json(receipts)
    profile_path = args.release_dir / KIT / 'profile.json'
    require(sha_file(profile_path) == receipt['sdk']['profile_file_sha256'], 'staged release profile differs')
    release_digest = sha_file(args.release_dir / 'release_manifest.json')
    require(release_digest == receipt['release_sha256'], 'staged release differs')
    return run_seed(args.seed_dir, args.output_dir, receipts, receipt, load_json(profile_path), release_digest)


def run_packaged(release_dir, output, python_source):
    release, profile = verify_assembled(release_dir)
    require('gnu_seed' in release, 'release has no packaged GNU Seed')
    images = release_dir / IMAGES
    path = images / SEED_RECEIPT
    return run_seed(images, output, path, load_json(path), profile,
                    sha_file(release_dir / 'release_manifest.json'), python_source=python_source)


def run_seed(seed, output, receipt_path, receipt, profile, release_digest, *, python_source=None):
    firmware = {INSTALLER: receipt['installer_iso'], ORDINARY: receipt['system']['iso']}
    for name, expected in firmware.items():
        require(sha_file(seed / name) == expected['sha256'], 'staged image differs: ' + name)
    glibc_version = profile['sdk_binding']['libc_version']
    source = seed / 'work_disk.img'
    require(sha_file(source) == receipt['work_disk_sha256'], 'staged disk differs')
    output.mkdir(parents=True, exist_ok=False)
    work = output / 'work_disk.img'
    report = {'status': 'failed', 'system': receipt['system'], 'sdk': receipt['sdk'],
              'seed_receipt_sha256': sha_file(receipt_path), 'release_manifest_sha256': release_digest,
              'initial_disk_sha256': receipt['work_disk_sha256'],
              'runner_sha256': sha_file(Path(__file__)), 'cases': []}
    guest = None

    def close():
        nonlocal guest
        guest.close()
        (output / (guest.name + '.serial.log')).write_bytes(guest.output)
        guest = None

    def case(name, cmd, *, lines=(), text=(), exit_code=0, timeout=600):
        print(name, flush=True)
        before = resources(guest)
        result = command(guest, cmd, b'kind=exited code=', timeout)
        pump(guest, 0.3)
        actual_code = check_result(result, exit_code, lines)
        require(all(item in result for item in text), 'missing guest output: ' + name)
        after = resources(guest)
        require(before == after, 'native tool leaked guest resources: ' + name)
        report['cases'].append({'name': name, 'command': cmd, 'exit_code': actual_code,
                                'resources': after, 'output': result.decode('utf-8', errors='replace')})

    try:
        sparse_copy(source, work)
        require(sha_file(work) == receipt['work_disk_sha256'], 'staged disk copy differs')
        files = fixture_files()
        if python_source is not None:
            python_fixture = output / 'release.py'
            python_fixture.write_text(python_source)
            files['/src/native/release.py'] = python_fixture
        with Disk(work, output) as disk:
            install(disk, files)
            disk.command('mkdir', '/out/native')
        report['fixtures'] = {name: sha_file(path) for name, path in files.items()}
        guest = boot(seed / INSTALLER, work, output, 'installer', receipt['system']['build_id'])
        report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        command(guest, 'sync', b'[files] sync=ok')
        close()
        report['initial_packages'] = verify_disk(work, profile, receipt['packages'])
        with Disk(work, output, read_only=True) as disk:
            for tool in ('dash', 'xypm'):
                exported = disk.export('/usr/bin/' + tool)
                require(sha_file(exported) == receipt[tool + '_sha256'], tool + ' differs after installer')
                exported.unlink()
        guest = boot(seed / ORDINARY, work, output, 'ordinary', receipt['system']['build_id'])
        c_ok = ('GLIBC_GNU_SEED_C=' + glibc_version).encode()
        if python_source is not None:
            case('release_python_before_native_builds', 'exec-file /usr/bin/python3 -B /src/native/release.py',
                 lines=(PYTHON_OK,))
        case('gcc_version', 'x86_64-elf-gcc --version', text=(b'16.2.0',))
        case('gxx_version', 'x86_64-elf-g++ --version', text=(b'16.2.0',))
        case('gnu_make_version', 'gmake --version', lines=(b'GNU Make 4.4.1',))
        for tool in ('as', 'ld', 'ar', 'ranlib'):
            case(tool + '_version', 'x86_64-elf-' + tool + ' --version', text=(b'GNU', b'2.47'))
        case('direct_c_compile_link', GCC + ' -v -I/src/native /src/native/project_c.c '
             '/src/native/project_value.c -o /out/native/direct_c.elf', text=(b'/cc1 ', b'/x86_64-elf-ld '))
        case('direct_c_execute', '/out/native/direct_c.elf', lines=(c_ok,))
        case('direct_cpp_compile_link', GXX + ' -v -std=gnu++20 /src/native/project_cpp.cpp '
             '/src/native/project_cpp_value.cpp -o /out/native/direct_cpp.elf',
             text=(b'/cc1plus ', b'/x86_64-elf-ld '))
        case('direct_cpp_execute', '/out/native/direct_cpp.elf', lines=(b'SL3_CPP_OK',))
        case('gnu_make_from_xsh', MAKE, lines=(b'GLIBC_GNU_SEED_MAKE_OK',))
        case('make_c_execute', '/out/native/c.elf', lines=(c_ok,))
        case('make_cpp_execute', '/out/native/cpp.elf', lines=(b'SL3_CPP_OK',))
        case('gnu_make_from_dash', 'dash /src/native/build.sh',
             lines=(b'GLIBC_GNU_SEED_MAKE_OK', c_ok, b'SL3_CPP_OK', b'GLIBC_GNU_SEED_DASH_OK'))
        case('undefined_symbol_rejected', GCC + ' /src/native/link_error.c -o /out/native/invalid.elf',
             text=(b'undefined reference',), exit_code=None)
        command(guest, 'sync', b'[files] sync=ok')
        close()
        guest = boot(seed / ORDINARY, work, output, 'reboot', receipt['system']['build_id'])
        case('cold_boot_c', '/out/native/c.elf', lines=(c_ok,))
        case('cold_boot_cpp', '/out/native/cpp.elf', lines=(b'SL3_CPP_OK',))
        if python_source is not None:
            case('release_python_after_native_builds_and_reboot', 'exec-file /usr/bin/python3 -B /src/native/release.py',
                 lines=(PYTHON_OK,))
        close()

        report['outputs'] = {}
        with Disk(work, output, read_only=True) as disk:
            require(disk.info('/out/native/invalid.elf') is None, 'failed link left an executable')
            for name in ('direct_c.elf', 'direct_cpp.elf', 'c.elf', 'cpp.elf', 'c.map', 'cpp.map', 'libvalue.a'):
                exported = disk.export('/out/native/' + name)
                saved = output / name
                exported.rename(saved)
                report['outputs'][name] = {'sha256': sha_file(saved), 'bytes': saved.stat().st_size}
                if name.endswith('.elf'):
                    verify_elf(saved)
                    require_stdio_marker(saved.read_bytes(), name)
                if name.endswith('.map'):
                    paths = (b'/sysroot/usr/lib/xos_start.o', b'/sysroot/usr/lib/libc.a')
                    if name == 'cpp.map':
                        paths += (b'/sysroot/usr/lib/libstdc++.a',)
                    body = saved.read_bytes()
                    require(all(path in body for path in paths) and b'/sysroot/lib/' not in body,
                            'link map differs from the selected glibc sysroot')
                if name == 'libvalue.a':
                    require(saved.read_bytes().startswith(b'!<arch>\n/ '), 'archive lacks a native symbol index')
        report['final_packages'] = verify_disk(work, profile, receipt['packages'])
        require(sha_file(source) == receipt['work_disk_sha256'], 'staged source disk was written')
        report.update(status='passed_subset', final_disk_sha256=sha_file(work))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest is not None:
            close()
        (output / 'report.json').write_bytes(canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('seed-dir', 'release-dir', 'output-dir'):
        parser.add_argument('--' + name, required=True, type=Path)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
