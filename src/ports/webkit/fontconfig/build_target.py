#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-build Fontconfig against the XOS FreeType and LibXml2 targets."""

import argparse
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

port = Path(__file__).resolve().parent
root = port.parents[3]
sys.path.insert(0, str(root / 'scripts'))
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def dependency(target, status, library, headers):
    manifest = target / 'manifest.json'
    data = manifest.read_bytes()
    record = json.loads(data)
    if record['status'] != status:
        raise ValueError(f'Incomplete {library} target build')
    prefix = target / 'prefix'
    artifacts = sorted((prefix / 'include' / headers).rglob('*.h')) + [prefix / 'lib' / library]
    if len(artifacts) < 2:
        raise ValueError(f'Missing {library} headers')
    inputs = {path: record['artifacts'][path.relative_to(target).as_posix()] for path in artifacts}
    inputs[manifest] = sha256(data).hexdigest()
    return inputs


def build(args):
    lock_path = port / 'source_lock.json'
    lock = json.loads(lock_path.read_bytes())
    if args.archive.stat().st_size != lock['archive_bytes'] or digest(args.archive) != lock['sha256']:
        raise ValueError('Fontconfig archive differs from the upstream source lock')

    sdk_manifest = args.sdk_build / 'manifest.json'
    sdk_record = json.loads(sdk_manifest.read_bytes())
    if sdk_record['status'] != 'static_sdk_built':
        raise ValueError('A complete static XOS glibc SDK is required')
    tools = {suffix: tool_identity('x86_64-elf-' + suffix) for suffix in ('gcc', 'as', 'ld', 'ar', 'ranlib')}
    for suffix, item in tools.items():
        if item.get('sha256') != sdk_record['tools']['x86_64-elf-' + suffix]['sha256']:
            raise ValueError(f'{suffix} differs from the selected SDK toolchain')
    tools['gperf'] = tool_identity('gperf')
    if not tools['gperf']['available']:
        raise ValueError('The build host requires GNU gperf')

    font_inputs = dependency(args.font_target, 'target_font_stack_linked', 'libfreetype.a', 'freetype2')
    xml_inputs = dependency(args.xml_target, 'target_libxml2_linked', 'libxml2.a', 'libxml2')
    sdk = args.sdk_build / 'sysroot'
    fixture = root / 'tests/fixtures/webkit/fontconfig_match.c'
    driver = port.parent / 'icu/xos-compiler'
    inputs = {**font_inputs, **xml_inputs, **{path: digest(path) for path in
              (sdk_manifest, driver, lock_path, fixture, sdk / 'usr/lib/libc.a')}}
    inputs[args.archive] = lock['sha256']

    def verify_inputs():
        for path, expected in inputs.items():
            if digest(path) != expected:
                raise ValueError(f'Input differs from its build receipt: {path.name}')

    verify_inputs()
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    work, binutils, headers = (output / name for name in ('autotools', 'binutils', 'prefix/include/fontconfig'))
    for directory in (work, binutils, headers):
        directory.mkdir(parents=True)
    lib = output / 'prefix/lib'
    lib.mkdir()
    cc = output / 'cc'
    cc.symlink_to(driver)
    for name in ('as', 'ld'):
        (binutils / name).symlink_to(tools[name]['path'])
    freetype = args.font_target / 'prefix'
    xml = args.xml_target / 'prefix'
    env, _ = clean_build_environment(os.environ)
    env.update(LC_ALL='C', CONFIG_SITE='/dev/null', PKG_CONFIG_LIBDIR=str(work),
               COMPILER_PATH=str(binutils), XOS_ICU_SDK=str(sdk), XOS_ICU_CC=tools['gcc']['path'],
               CC=str(cc), AR=tools['ar']['path'], RANLIB=tools['ranlib']['path'],
               FREETYPE_CFLAGS='-I' + shlex.quote(str(freetype / 'include/freetype2')),
               FREETYPE_LIBS=shlex.quote(str(freetype / 'lib/libfreetype.a')),
               LIBXML2_CFLAGS='-I' + shlex.quote(str(xml / 'include/libxml2')),
               LIBXML2_LIBS=shlex.quote(str(xml / 'lib/libxml2.a')))

    def run(stage, command):
        log = output / (stage + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=work, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{stage} failed; see {log}')

    run('unpack', ['tar', '-xf', args.archive, '-C', output])
    source = output / lock['archive_root']
    notice = source / lock['license_member']
    if digest(notice) != lock['license_sha256']:
        raise ValueError('Fontconfig notice differs from the upstream source lock')
    build_host = subprocess.check_output([source / 'config.guess'], env=env, text=True).strip()
    run('configure', [source / 'configure', '--build=' + build_host, '--host=x86_64-elf',
                      '--prefix=/usr', '--sysconfdir=/etc', '--localstatedir=/var',
                      '--disable-shared', '--enable-static',
                      '--disable-docs', '--disable-cache-build', '--enable-libxml2',
                      '--with-default-fonts=/usr/share/fonts'])
    run('compile', ['make', '-j' + str(args.jobs), '-C', 'src'])
    archive = lib / 'libfontconfig.a'
    shutil.copyfile(work / 'src/.libs/libfontconfig.a', archive)
    for header in ('fontconfig.h', 'fcfreetype.h', 'fcprivate.h'):
        shutil.copyfile(source / 'fontconfig' / header, headers / header)
    installed_notice = output / 'prefix/share/licenses/fontconfig/COPYING'
    installed_notice.parent.mkdir(parents=True)
    shutil.copyfile(notice, installed_notice)
    elf = output / 'fontconfig_match.elf'
    run('link', [cc, '-std=c17', '-O2', '-I', headers.parent, fixture, archive,
                 freetype / 'lib/libfreetype.a', xml / 'lib/libxml2.a', '-o', elf])
    verify_elf(elf)
    verify_inputs()
    artifacts = [elf, *(path for path in sorted((output / 'prefix').rglob('*')) if path.is_file())]
    receipt = {'status': 'target_fontconfig_linked', 'archive_sha256': lock['sha256'],
               'source_lock_sha256': inputs[lock_path], 'sdk_manifest_sha256': inputs[sdk_manifest],
               'sdk_libc_sha256': inputs[sdk / 'usr/lib/libc.a'],
               'fixture_sha256': inputs[fixture], 'license_sha256': lock['license_sha256'],
               'build_recipe_sha256': digest(Path(__file__)), 'compiler_wrapper_sha256': inputs[driver],
               'font_target_manifest_sha256': font_inputs[args.font_target / 'manifest.json'],
               'xml_target_manifest_sha256': xml_inputs[args.xml_target / 'manifest.json'],
               'tools': {name: item['sha256'] for name, item in tools.items()},
               'artifacts': {path.relative_to(output).as_posix(): digest(path) for path in artifacts}}
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sdk-build', 'font-target', 'xml-target', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--jobs', default=2, type=int)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    build(args)
