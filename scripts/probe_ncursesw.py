#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Explore ncurses 6.5 cross-configuration against an explicit XOS SDK.

This is a build-time probe, not a port or guest acceptance. The output directory
must not exist; no existing SDK or system build is modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / 'src/ports/ncurses/source_lock.json'
LOCK = json.loads(LOCK_PATH.read_text())
SOURCE_URL = LOCK['source_url']
SOURCE_SHA256 = LOCK['archive_sha256']


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True,
                        help='new private output directory; must not already exist')
    parser.add_argument('--build', action='store_true',
                        help='also attempt target library compilation (still not acceptance)')
    args = parser.parse_args()
    lock_hash = digest(LOCK_PATH)
    archive, sdk, work = args.archive.resolve(), args.sdk.resolve(), args.output.resolve()
    if (work.is_relative_to(ROOT / 'src') or work.is_relative_to(ROOT / 'localpilot')
            or work.is_relative_to(sdk)):
        raise SystemExit('output must be outside src, localpilot and the selected SDK')
    if digest(archive) != SOURCE_SHA256:
        raise SystemExit('ncurses archive does not match the selected probe source')
    for item in ('include', 'lib/libc.a', 'lib/libm.a', 'lib/libxos.a',
                 'lib/libxos_loader.a', 'crt0_posix.o', 'user.ld', 'manifest.json'):
        if not (sdk / item).exists():
            raise SystemExit('SDK is missing ' + item)
    sdk_tree, _ = tree_receipt(sdk)
    if digest(ROOT / 'src/ports/ncurses' / LOCK['notice']) != LOCK['notice_sha256']:
        raise SystemExit('stored upstream notice does not match lock')
    cc = shutil.which('x86_64-elf-gcc')
    cc_build = shutil.which('cc')
    target_as, target_ld = (shutil.which('x86_64-elf-' + n) for n in ('as', 'ld'))
    if not all((cc, cc_build, target_as, target_ld)):
        raise SystemExit('target or build compiler tools are unavailable')
    work.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive) as source_archive:
        source_archive.extractall(work, filter='data')
    source = work / 'ncurses-6.5'
    if digest(source / 'COPYING') != LOCK['notice_sha256']:
        raise SystemExit('upstream archive notice does not match lock')
    build = work / 'build'
    build.mkdir()
    tools = work / 'target_tools'
    tools.mkdir()
    (tools / 'as').symlink_to(Path(target_as).resolve())
    (tools / 'ld').symlink_to(Path(target_ld).resolve())
    build_triplet = subprocess.check_output([str(source / 'config.guess')], text=True).strip()
    libgcc = subprocess.check_output([cc, '-print-libgcc-file-name'], text=True).strip()
    flags = ['-B' + str(tools) + '/', '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic',
             '-fno-stack-protector', '-ffunction-sections', '-fdata-sections']
    ldflags = ['-nostdlib', '-static', '-no-pie',
               '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
               '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o')]
    libs = ['-Wl,--start-group'] + [str(sdk / 'lib' / n) for n in
             ('libxos.a', 'libxos_loader.a', 'libc.a', 'libm.a')] + [libgcc, '-Wl,--end-group']
    env = dict(os.environ)
    env.pop('COMPILER_PATH', None)
    env.update(CC=cc, BUILD_CC=cc_build, CFLAGS=shlex.join(flags),
               CPPFLAGS=shlex.join(['-isystem', str(sdk / 'include')]),
               LDFLAGS=shlex.join(ldflags), LIBS=shlex.join(libs))
    command = [str(source / 'configure'), '--build=' + build_triplet,
               '--host=x86_64-unknown-elf', '--enable-widec', '--without-shared',
               '--without-cxx', '--without-cxx-binding', '--without-ada',
               '--without-progs', '--without-tests', '--without-debug']
    with (work / 'configure.log').open('w') as log:
        result = subprocess.run(command, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
    build_exit_code = None
    if result.returncode == 0 and args.build:
        with (work / 'make.log').open('w') as log:
            build_exit_code = subprocess.run(['make', '-j2'], cwd=build, env=env,
                                             stdout=log, stderr=subprocess.STDOUT).returncode
    inputs_unchanged = tree_receipt(sdk)[0] == sdk_tree and digest(LOCK_PATH) == lock_hash
    report = {'kind': 'cross_configuration_probe_only', 'source_url': SOURCE_URL,
              'source_lock_sha256': lock_hash, 'sdk_tree_sha256': sdk_tree,
              'inputs_unchanged': inputs_unchanged,
              'source_sha256': SOURCE_SHA256, 'sdk_manifest_sha256': digest(sdk / 'manifest.json'),
              'sdk_libc_sha256': digest(sdk / 'lib/libc.a'), 'target_compiler': cc,
              'build_compiler': cc_build, 'configure_command': command,
              'environment': {k: env[k] for k in ('CC', 'BUILD_CC', 'CFLAGS', 'CPPFLAGS', 'LDFLAGS', 'LIBS')},
              'configure_exit_code': result.returncode, 'build_exit_code': build_exit_code,
              'guest_run': False,
              'note': 'Configure probes do not establish target runtime semantics or a supported port.'}
    (work / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return result.returncode or (build_exit_code or 0) or (0 if inputs_unchanged else 1)


if __name__ == '__main__':
    raise SystemExit(main())
