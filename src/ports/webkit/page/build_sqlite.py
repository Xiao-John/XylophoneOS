#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build locked SQLite with the real XOS Files VFS for one renderer process."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
SQLITE = ROOT / 'src/ports/cpython/sqlite'
sys.path[:0] = [str(ROOT / 'scripts'), str(PORT.parent)]
from glibc_g1_probe import clean_build_environment, tool_identity
from target_inputs import digest, recheck_inputs
from xypm_sdk_profile import metadata_snapshot, verify_profile


def build(args):
    lock, lock_hash = metadata_snapshot(SQLITE / 'sqlite_lock.json')
    if digest(args.archive) != lock['sha256'] or args.archive.stat().st_size != lock['archive_bytes']:
        raise ValueError('SQLite archive differs from its source lock')
    profile, profile_hash = metadata_snapshot(args.sdk_profile)
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    manifest, sdk_hash = metadata_snapshot(args.sdk_build / 'manifest.json', profile['sdk_binding']['sdk_manifest_sha256'])
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib')}
    for name, actual in tools.items():
        if actual.get('sha256') != manifest['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('SQLite tool differs from SDK: ' + name)
    if 'threads' not in profile['features']:
        raise ValueError('SQLite requires the real pthread SDK')
    driver = PORT.parent / 'icu/xos-compiler'
    inputs = {args.archive: lock['sha256'], SQLITE / 'sqlite_lock.json': lock_hash,
              args.sdk_profile: profile_hash, args.sdk_build / 'manifest.json': sdk_hash}
    for path in (Path(__file__), driver, SQLITE / 'xos_vfs.c', SQLITE / 'UPSTREAM_LICENSE.md'):
        inputs[path] = digest(path)
    recheck_inputs(inputs)
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    source, drivers, prefix = out / 'source', out / 'drivers', out / 'prefix'
    source.mkdir(); (drivers / 'binutils').mkdir(parents=True)
    (prefix / 'lib').mkdir(parents=True); (prefix / 'include').mkdir()
    with tarfile.open(args.archive) as archive:
        archive.extractall(source, filter='data')
    source = source / args.archive.name.removesuffix('.tar.gz')
    for name in ('cc', 'cxx'):
        (drivers / name).symlink_to(driver)
    for name in ('as', 'ld'):
        (drivers / 'binutils' / name).symlink_to(tools[name]['path'])
    includes = drivers / 'cxx-includes.txt'
    includes.write_text('\n'.join(profile['sdk_binding']['cxx_runtime']['include_directories']) + '\n')
    env, removed = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(drivers / 'binutils'), XOS_ICU_SDK=str(args.sdk_build / 'sysroot'),
               XOS_ICU_CC=tools['gcc']['path'], XOS_ICU_CXX=tools['g++']['path'], XOS_ICU_CXX_INCLUDES=str(includes))
    flags = ['-O2', '-g0', '-ffunction-sections', '-fdata-sections', '-DSQLITE_OS_OTHER=1',
             '-DSQLITE_THREADSAFE=1', '-DSQLITE_OMIT_LOAD_EXTENSION=1', '-DSQLITE_OMIT_WAL=1',
             '-DSQLITE_TEMP_STORE=3', '-DSQLITE_DQS=0', '-I', source]
    steps = []

    def run(name, command):
        command = list(map(str, command))
        log = out / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        steps.append({'stage': name, 'command': command, 'returncode': result.returncode, 'log_sha256': digest(log)})
        if result.returncode:
            raise RuntimeError(name + ' failed; see ' + str(log))

    for name, path in (('sqlite3', source / 'sqlite3.c'), ('xos_vfs', SQLITE / 'xos_vfs.c')):
        run(name, [drivers / 'cc', *flags, '-c', path, '-o', out / (name + '.o')])
    run('archive', [tools['ar']['path'], 'rcsD', prefix / 'lib/libsqlite3.a', out / 'sqlite3.o', out / 'xos_vfs.o'])
    for name in ('sqlite3.h', 'sqlite3ext.h'):
        shutil.copyfile(source / name, prefix / 'include' / name)
    notices = prefix / 'share/licenses/sqlite'; notices.mkdir(parents=True)
    shutil.copyfile(SQLITE / 'UPSTREAM_LICENSE.md', notices / 'UPSTREAM_LICENSE.md')
    recheck_inputs(inputs)
    if verify_profile(profile, 'glibc', args.sdk_build) != binding:
        raise ValueError('SDK changed during SQLite build')
    artifacts = {path.relative_to(out).as_posix(): digest(path) for path in prefix.rglob('*') if path.is_file()}
    record = {'status': 'static_sqlite_built', 'sdk_tree_sha256': binding['sdk_tree_sha256'],
              'sdk_manifest_sha256': sdk_hash, 'sdk_profile_sha256': profile_hash,
              'inputs': {str(path.relative_to(ROOT)): value for path, value in inputs.items()},
              'steps': steps, 'sanitized_environment': removed, 'artifacts': artifacts,
              'vfs_scope': 'one renderer process; exclusive rollback journal; no WAL or load extensions',
              'guest_qualification': 'not_run'}
    (out / 'manifest.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sdk-build', 'sdk-profile', 'output'):
        parser.add_argument('--' + name, required=True, type=lambda value: Path(value).resolve())
    build(parser.parse_args())
