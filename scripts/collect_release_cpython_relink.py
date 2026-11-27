#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Archive exact CPython link objects bound to an installed-release XPK."""

import argparse
from gzip import GzipFile
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import shlex
import tarfile
from tempfile import TemporaryDirectory

from package_cpython_glibc import PACKAGE, PROGRAM, RECEIPT
from relink_release_xypm import CPYTHON_FORMAT, LIBC, LINK_FLAGS
from xypm_format import canonical, confined, load_json, require, sha_file, strict_json, verify_package

SCRIPTS = Path(__file__).resolve().parent
LINK_LIBRARIES = {'-ldl': 'libdl.a', '-lpthread': 'libpthread.a', '-lm': 'libm.a'}
COMPILE_FLAGS = ['-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector', '-ftls-model=local-exec']
HELPERS = ('relink_release_cpython.py', 'relink_release_xypm.py', 'glibc_g1_probe.py', 'glibc_g1_deps.py',
           'package_cpython_glibc.py', 'build_cpython_legacy.py', 'build_cpython_zlib.py', 'stage_cpython.py',
           'xypm_format.py', 'xypm_sdk_profile.py', 'xos_app.py', 'archive_member_map.py', 'verify_glibc_source.py')


def make_link(log, report):
    step, = (item for item in report['steps'] if item['name'] == 'target_make')
    require(step['exit_code'] == 0 and hashlib.sha256(log).hexdigest() == step['log_sha256'],
            'target make log differs from the CLI receipt')
    compiler = report['tools']['gcc']['path']
    command, = (shlex.split(line) for line in log.decode().splitlines()
                if line.startswith(compiler + ' ') and ' -o python ' in line)
    return command


def link_plan(command, donor, build, sysroot, artifacts):
    require(command[1].startswith('--sysroot=') and command[2].startswith('-B')
            and command[3:3 + len(COMPILE_FLAGS)] == COMPILE_FLAGS and command.count('-o') == 1,
            'unexpected CPython link driver')
    recorded_sdk = PurePosixPath(command[1].removeprefix('--sysroot='))
    recorded_build = PurePosixPath(donor['executable']['path']).parent.parent
    index = command.index('-o')
    require(recorded_sdk.is_absolute() and recorded_build.is_absolute()
            and PurePosixPath(command[2].removeprefix('-B')) == recorded_build / 'tools'
            and command[index + 1] == 'python', 'unexpected CPython build paths')
    plan, sources = [], {}
    for value in command[3 + len(COMPILE_FLAGS):index] + command[index + 2:]:
        if value in LINK_FLAGS:
            plan.append(value)
            continue
        path = (recorded_sdk / 'usr/lib' / LINK_LIBRARIES[value]
                if value in LINK_LIBRARIES else PurePosixPath(value))
        require(path.suffix in ('.o', '.a', '.ld'), 'unexpected CPython link input: ' + value)
        if path.is_relative_to(recorded_sdk):
            relative = path.relative_to(recorded_sdk).as_posix()
            incoming = confined(sysroot, relative)
            require(sha_file(incoming) == artifacts[relative], 'SDK link input differs: ' + relative)
            name = 'sysroot/' + relative
        elif path.is_absolute():
            require(path.is_relative_to(recorded_build), 'unexpected absolute CPython link object')
            relative = path.relative_to(recorded_build).as_posix()
            require(relative in ('xos_time.o', 'zlib/lib/libz.a'), 'unexpected external CPython object')
            incoming = confined(build, relative)
            name = 'objects/' + relative
        else:
            require(path.parts[0] in ('Programs', 'Modules', 'Objects', 'Parser', 'Python') and path.suffix in ('.o', '.a'),
                    'unexpected CPython target object')
            incoming = confined(build, 'target_build/' + path.as_posix())
            name = 'objects/target/' + path.as_posix()
        sources[name] = incoming
        plan.append({'file': name})
    require({'objects/target/Programs/python.o', 'objects/xos_time.o', 'objects/zlib/lib/libz.a', LIBC}
            <= sources.keys(), 'incomplete CPython link')
    require(sha_file(sources['objects/zlib/lib/libz.a']) == donor['zlib']['artifacts']['lib/libz.a'],
            'actual zlib archive differs from the build receipt')
    return plan, sources


def package_bindings(package_path, digest, profile):
    bodies = {}

    def capture(event, item, data):
        if item['path'] == RECEIPT or item['path'].startswith('usr/share/licenses/' + PACKAGE + '/'):
            name = item['path']
            if event == 'begin':
                bodies[name] = bytearray()
            elif event == 'data':
                require(len(bodies[name]) + len(data) <= 1 << 20, 'unexpectedly large CPython receipt or notice')
                bodies[name].extend(data)

    manifest = verify_package(package_path, profile, expected_sha256=digest, sink=capture)['manifest']
    binary, = (item for item in manifest['files'] if item['role'] == 'executable')
    require(manifest['id'] == PACKAGE and binary['path'] == PROGRAM
            and manifest['build_receipt']['path'] == RECEIPT, 'wrong CPython release package')
    receipt = bytes(bodies.pop(RECEIPT))
    require(set(bodies) == set(manifest['licenses']), 'CPython notice set differs from the release')
    return binary, receipt, bodies


def collect(args):
    release_path = confined(args.release, 'release_manifest.json')
    require(sha_file(release_path) == args.sha256, 'release manifest differs')
    release = load_json(release_path)
    sdk = args.release / 'application-sdk/sdk'
    profile_path = confined(sdk.parent, 'profile.json')
    profile = load_json(profile_path)
    meta_path = confined(sdk, 'manifest.json')
    metadata = load_json(meta_path)
    binding = release['application_sdk']
    require(sha_file(meta_path) == binding['sdk_manifest_sha256']
            and sha_file(profile_path) == binding['profile_file_sha256'], 'release SDK or profile differs')
    package_path = confined(args.release, 'packages/cpython.xpk')
    package_digest = release['packages']['cpython']['sha256']
    elf, receipt_bytes, notices = package_bindings(package_path, package_digest, profile)
    package = strict_json(receipt_bytes)
    interpreter = package['interpreter']
    require(interpreter['sha256'] == elf['sha256'] and interpreter['bytes'] == elf['size']
            and interpreter['strip_mode'] == 'strip-debug'
            and interpreter['objcopy_sha256'] == metadata['tools']['x86_64-elf-objcopy']['sha256'],
            'CPython package runtime or strip tool differs')
    frozen_path = confined(args.frozen, 'cpython-cli.json')
    require(sha_file(frozen_path) == package['cli_build_receipt_sha256'], 'serial CLI receipt differs')
    frozen = load_json(frozen_path)
    donor_path = confined(args.donor, 'py0a_report.json')
    donor = load_json(donor_path)
    for receipt in (frozen, donor):
        require(receipt['status'] == 'built_not_run' and receipt['version'] == '3.14.9'
                and receipt['runtime_family'] == 'glibc' and receipt['target'] == 'x86_64-unknown-xos'
                and receipt['sdk_manifest_sha256'] == package['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
                and receipt['profile_file_sha256'] == package['profile_file_sha256'] == binding['profile_file_sha256']
                and receipt['executable']['sha256'] == interpreter['debug_sha256']
                and receipt['executable']['bytes'] == interpreter['debug_bytes']
                and receipt['source_archive_sha256'] == package['source_archive_sha256']
                and receipt['zlib'] == package['zlib'], 'retained object donor differs from the released build')
    donor_elf = confined(args.donor, 'target_build/python.exe')
    require(sha_file(donor_elf) == interpreter['debug_sha256'], 'retained debug ELF differs from the released build')
    donor_log = confined(args.donor, 'target_make.log')
    frozen_log = confined(args.frozen, 'target_make.log.gz')
    with GzipFile(filename=frozen_log) as archive:
        serial_link = make_link(archive.read(1 << 20), frozen)
    donor_link = make_link(donor_log.read_bytes(), donor)
    require(donor_link == serial_link, 'retained and released link commands differ')
    tools = {name: donor['tools'][name]['sha256'] for name in ('gcc', 'as', 'ld')}
    require(all(digest == frozen['tools'][name]['sha256'] == metadata['tools']['x86_64-elf-' + name]['sha256']
                for name, digest in tools.items()), 'CPython link tools differ from the release')

    plan, sources = link_plan(donor_link, donor, args.donor, sdk / 'sysroot', metadata['artifacts'])
    sources.update({'receipt/release_manifest.json': release_path, 'receipt/sdk_manifest.json': meta_path,
                    'receipt/profile.json': profile_path, 'receipt/cpython-cli.json': frozen_path,
                    'receipt/object_donor.json': donor_path, 'receipt/donor_make.log': donor_log,
                    'receipt/frozen_make.log.gz': frozen_log})
    sources.update({'tools/' + name: SCRIPTS / name for name in HELPERS})
    embedded = {'receipt/package.json': receipt_bytes}
    embedded.update({'licenses/' + name: bytes(data) for name, data in notices.items()})
    files = {name: sha_file(path) for name, path in sources.items()}
    files.update({name: hashlib.sha256(data).hexdigest() for name, data in embedded.items()})
    manifest = {'format': CPYTHON_FORMAT, 'plan': plan, 'tools': tools, 'files': files,
                'reference': interpreter['debug_sha256'], 'interpreter': interpreter,
                'cpython_xpk_sha256': package_digest}
    embedded['manifest.json'] = canonical(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'choose new CPython materials archive')
    with TemporaryDirectory(dir=args.output.parent) as directory:
        packed = Path(directory) / 'materials.tar.gz'
        with packed.open('xb') as raw, GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed, \
                tarfile.open(fileobj=compressed, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
            for name in sorted(sources.keys() | embedded.keys()):
                info = tarfile.TarInfo(name)
                if name in embedded:
                    data = embedded[name]
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
                else:
                    with sources[name].open('rb') as source:
                        info.size = os.fstat(source.fileno()).st_size
                        archive.addfile(info, source)
        os.link(packed, args.output)
    print(hashlib.sha256(embedded['manifest.json']).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'donor', 'frozen', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--sha256', required=True)
    collect(parser.parse_args())


if __name__ == '__main__':
    main()
