#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage the published native GNU Seed and a selected glibc SDK on a new work disk."""
import argparse
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

from package_glibc_release import INSTALLER, KIT, ORDINARY, copy_bound, verify_assembled, verify_disk
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import COMPILER_VERSION, GLIBC_CRT, relative_file, require_stdio_marker

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / 'docs/releases/release_0_0_2_1103.json'
TARGET = 'x86_64-elf'
DRIVER_DIR = '/usr/lib/gcc/' + TARGET + '/' + COMPILER_VERSION
FRONTEND_DIR = '/usr/libexec/gcc/' + TARGET + '/' + COMPILER_VERSION
TOOLS = tuple('/usr/bin/' + TARGET + '-' + name for name in (
    'gcc', 'g++', 'cpp', 'as', 'ld', 'ar', 'ranlib', 'nm', 'strip',
)) + ('/usr/bin/as', FRONTEND_DIR + '/cc1', FRONTEND_DIR + '/cc1plus')
LICENSES = ('gcc', 'binutils', 'gmp', 'mpfr', 'mpc')
SYSROOT = '/sysroot'
MAKE_PATH = '/usr/bin/gmake'


def copy_sparse(source, output, size):
    with output.open('xb') as dest:
        remaining = size
        while remaining:
            block = source.read(min(1 << 20, remaining))
            require(block, 'truncated disk image')
            if block.count(0) == len(block):
                dest.seek(len(block), os.SEEK_CUR)
            else:
                dest.write(block)
            remaining -= len(block)
        dest.truncate(size)


def driver_specs(profile):
    binding = profile['sdk_binding']
    start = (*GLIBC_CRT[:4], 'xos_stdio_receiver.o')
    libraries = ('libstdc++.a', 'libsupc++.a', 'libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a')
    if 'usr/lib/libgcc_eh.a' in binding['link_artifacts']:
        libraries += ('libgcc_eh.a',)
    def target_link(files):
        require(all('usr/lib/' + name in binding['link_artifacts'] for name in files),
                'glibc profile is missing a Seed link input')
        return ' '.join(SYSROOT + '/usr/lib/' + name for name in files)

    cxx_includes = ' '.join('-isystem ' + SYSROOT + '/' + path
                            for path in binding['cxx_runtime']['include_directories'])
    common = '-mno-red-zone -fno-pie -fno-pic -ftls-model=local-exec'
    return f'''# SPDX-License-Identifier: Apache-2.0
# Target XOS static glibc. The compiler programs have their own static runtime.
*cc1:
-nostdinc -idirafter {SYSROOT}/usr/include -idirafter {SYSROOT}/usr/lib/compiler-include {common}

*cc1plus:
-nostdinc++ {cxx_includes}

*link:
%{{shared|pie|static-pie:%eXOS GNU Seed supports static non-PIE executables only}} -m elf_x86_64 -static -T {SYSROOT}/user.ld -L {SYSROOT}/usr/lib --build-id=none -z noexecstack -z max-page-size=4096

*linker:
/usr/bin/{TARGET}-ld

*startfile:
{target_link(start)}

*endfile:
{target_link(GLIBC_CRT[4:])}

*link_gcc_c_sequence:
--start-group {target_link(libraries)} --end-group

'''


def donor_artifacts(folder, work, receipt):
    frozen = {item['name']: item for item in receipt['assets']}
    archive_name = 'xylophoneos_revival_' + receipt['version'] + '_images'
    paths = {}
    for name in ('release_manifest.json', archive_name + '.tar.gz'):
        path = relative_file(folder, name)
        expected = frozen[name]
        require(path.stat().st_size == expected['bytes'] and sha_file(path) == expected['sha256'],
                'published Seed asset differs from the frozen receipt: ' + name)
        paths[name] = path

    info = load_json(paths['release_manifest.json'])
    require(info['system_build_id'] == receipt['system_build_id'], 'published Seed identity differs')
    with tarfile.open(paths[archive_name + '.tar.gz'], 'r|gz') as archive:
        entry = next((item for item in archive if item.name == archive_name + '/work_disk.img'), None)
        require(entry is not None, 'frozen asset has no work disk')
        require(entry.isfile() and entry.size == 2048 << 20, 'invalid frozen Seed work image')
        with archive.extractfile(entry) as image:
            donor_disk = work / 'donor.img'
            copy_sparse(image, donor_disk, entry.size)
    files = info['guest_files']
    selected = (*TOOLS, *(name for name in files
                         if name.startswith(tuple('/usr/share/licenses/' + item + '/' for item in LICENSES))))
    staged = {}
    with Disk(donor_disk, work, read_only=True) as disk:
        for name in selected:
            source = disk.export(name)
            require(sha_file(source) == files[name], 'published Seed guest file differs: ' + name)
            staged[name] = source
    return staged


def bind_make(receipt, profile_digest, kit):
    record = load_json(receipt)
    lock = load_json(ROOT / 'src/ports/gnu_make/source_lock.json')
    for key, expected in (
        ('status', 'built_not_run'), ('version', lock['version']), ('archive_sha256', lock['sha256']),
        ('signature_sha256', lock['signature_sha256']),
        ('source_verified_signer', lock['signer_primary_fingerprint']),
        ('profile_sha256', profile_digest), ('sdk_manifest_sha256', kit['sdk_manifest_sha256']),
        ('sdk_tree_sha256', kit['sdk_tree_sha256']),
    ):
        require(record[key] == expected, 'GNU Make receipt mismatch: ' + key)
    elf = relative_file(receipt.parent, record['elf']['path'])
    require(sha_file(elf) == record['elf']['sha256'], 'GNU Make ELF differs')
    require_stdio_marker(elf.read_bytes(), 'GNU Make')
    return elf, record['elf']['sha256']


def install(disk, files):
    parents = {path for name in files for path in Path(name).parents if path != Path('/')}
    for path in sorted(parents, key=lambda p: (len(p.parts), p.as_posix())):
        name = path.as_posix()
        info = disk.info(name)
        if info is None:
            disk.command('mkdir', name)
        else:
            require(info['directory'], 'Seed destination parent is a file: ' + name)
    for name, source in files.items():
        require(disk.info(name) is None, 'Seed destination already exists: ' + name)
        disk.command('import', name, source)


def prepare(release_dir, donor_dir, make_receipt, output):
    release, profile = verify_assembled(release_dir)
    require('cxx_runtime' in profile['features'], 'GNU Seed requires a unified C/C++ SDK')
    kit_binding = release['application_sdk']
    make, make_digest = bind_make(make_receipt, kit_binding['profile_file_sha256'], kit_binding)
    sdk = release_dir / KIT / 'sdk' / 'sysroot'
    source_disk = release_dir / 'images' / 'work_disk.img'
    image = release_dir / 'images' / ORDINARY
    donor_receipt = load_json(FROZEN)
    release_manifest = release_dir / 'release_manifest.json'
    report = {'status': 'assembled_unqualified', 'release_sha256': sha_file(release_manifest),
              'system': release['system'], 'sdk': kit_binding, 'candidate_source_commit': release['candidate_source_commit'],
              'installer_iso': release['installer_iso'], 'dash_sha256': release['dash_sha256'],
              'xypm_sha256': release['xypm_sha256'], 'packages': release['packages'],
              'donor': donor_receipt, 'make_receipt_sha256': sha_file(make_receipt),
              'preparation_sha256': sha_file(Path(__file__))}
    output.mkdir(parents=True, exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(dir=output) as temporary:
            work = Path(temporary)
            files = donor_artifacts(donor_dir, work, donor_receipt)
            specs = work / 'specs'
            specs.write_text(driver_specs(profile))
            files.update({DRIVER_DIR + '/specs': specs, MAKE_PATH: make,
                          SYSROOT + '/xos-profile.json': release_dir / KIT / 'profile.json',
                          SYSROOT + '/xos-sdk-manifest.json': sdk.parent / 'manifest.json',
                          '/usr/share/licenses/gnu_make/COPYING': relative_file(make_receipt.parent, 'COPYING')})
            for path in sorted(sdk.rglob('*')):
                relative = path.relative_to(sdk).as_posix()
                if path.is_file() and (relative.startswith(('usr/include/', 'usr/lib/compiler-include/'))
                                       or relative in profile['sdk_binding']['link_artifacts']):
                    files[SYSROOT + '/' + relative] = path
            disk_path = output / 'work_disk.img'
            with source_disk.open('rb') as source:
                copy_sparse(source, disk_path, release['work_disk']['bytes'])
            require(sha_file(disk_path) == release['work_disk']['sha256'], 'release work disk changed before staging')
            with Disk(disk_path, work) as disk:
                install(disk, files)
            hashes = {name: sha_file(path) for name, path in files.items()}
            require(hashes[MAKE_PATH] == make_digest, 'GNU Make changed before staging')
            require(hashes[SYSROOT + '/xos-profile.json'] == kit_binding['profile_file_sha256']
                    and hashes[SYSROOT + '/xos-sdk-manifest.json'] == kit_binding['sdk_manifest_sha256'],
                    'glibc SDK metadata changed before staging')
            with Disk(disk_path, work, read_only=True) as disk:
                for name, expected in hashes.items():
                    extracted = disk.export(name)
                    require(sha_file(extracted) == expected, 'installed Seed differs: ' + name)
                    extracted.unlink()
            verify_disk(disk_path, profile, release['packages'])
            copy_bound(image, output / ORDINARY, release['system']['iso']['sha256'])
            copy_bound(release_dir / 'images' / INSTALLER, output / INSTALLER, release['installer_iso']['sha256'])
            report.update(installed_files=hashes, work_disk_sha256=sha_file(disk_path))
        require(verify_assembled(release_dir) == (release, profile)
                and sha_file(release_manifest) == report['release_sha256'], 'release inputs changed during staging')
        (output / 'seed_receipt.json').write_bytes(canonical(report))
    except BaseException:
        shutil.rmtree(output)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release-dir', 'donor-dir', 'make-receipt', 'output-dir'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare(args.release_dir, args.donor_dir, args.make_receipt, args.output_dir)
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, 'GNU Seed preparation failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
