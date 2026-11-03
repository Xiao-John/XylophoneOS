#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build pinned host tic and generate a private xterm terminfo candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / 'src/ports/ncurses/source_lock.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--target-probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error('--jobs must be between 1 and 16')
    archive, output = args.archive.resolve(strict=True), args.output.resolve()
    target_probe = args.target_probe.resolve(strict=True)
    if output.exists() or any(output.is_relative_to(p) for p in (ROOT / 'src', ROOT / 'localpilot', target_probe)):
        raise SystemExit('output must be a new private directory outside src and localpilot')
    lock = json.loads(LOCK_PATH.read_text())
    if sha(archive) != lock['archive_sha256'] or lock['version'] != '6.5':
        raise SystemExit('ncurses source does not match the selected lock')
    target_report_path = target_probe / 'report.json'
    target_report = json.loads(target_report_path.read_text())
    target_config = target_probe / 'build/include/ncurses_cfg.h'
    target_library = target_probe / 'build/lib/libncursesw.a'
    target_config_text = target_config.read_text()
    if (target_report.get('archive_valid') is not True or
        target_report.get('source_sha256') != lock['archive_sha256'] or
        target_report.get('archive_sha256') != sha(target_library) or
        '#define MIXEDCASE_FILENAMES 1' not in target_config_text or
        '#define NCURSES_XNAMES 1' not in target_config_text):
        raise SystemExit('target probe configuration is not the selected single-xterm layout')
    tools = {name: shutil.which(name) for name in ('cc', 'make', 'ar', 'ranlib')}
    if not all(tools.values()):
        raise SystemExit(f'host build tool missing: {tools}')
    output.mkdir(parents=True)
    result = {'status': 'failed', 'guest_run': False, 'source_sha256': sha(archive),
              'source_lock_sha256': sha(LOCK_PATH), 'target_report_sha256': sha(target_report_path),
              'target_config_sha256': sha(target_config), 'target_library_sha256': sha(target_library),
              'commands': [], 'tools': tools}
    try:
        with tarfile.open(archive) as source_archive:
            source_archive.extractall(output, filter='data')
        source = output / 'ncurses-6.5'
        if sha(source / 'COPYING') != lock['notice_sha256']:
            raise RuntimeError('upstream notice does not match the lock')
        build = output / 'host_build'
        build.mkdir()
        env = dict(os.environ)
        for key in ('CC', 'CXX', 'CFLAGS', 'CPPFLAGS', 'LDFLAGS', 'LIBS', 'AR', 'RANLIB',
                    'COMPILER_PATH', 'TERMINFO', 'TERMINFO_DIRS', 'NCURSES_ROOT'):
            env.pop(key, None)
        env.update(CC=tools['cc'], AR=tools['ar'], RANLIB=tools['ranlib'], LC_ALL='C')
        commands = [
            [str(source / 'configure'), '--prefix=' + str(output / 'unused_install'), '--without-shared',
             '--with-normal', '--without-debug', '--without-cxx', '--without-cxx-binding',
             '--without-ada', '--without-tests', '--without-manpages', '--enable-mixed-case'],
            [tools['make'], '-j' + str(args.jobs)],
        ]
        for index, command in enumerate(commands):
            result['commands'].append(command)
            with (output / ('configure.log' if index == 0 else 'make.log')).open('w') as log:
                subprocess.run(command, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        tic, infocmp = build / 'progs/tic', build / 'progs/infocmp'
        versions = {tool.name: subprocess.check_output([str(tool), '-V'], env=env, text=True).strip()
                    for tool in (tic, infocmp)}
        if not all(value.startswith('ncurses 6.5.') or value == 'ncurses 6.5' for value in versions.values()):
            raise RuntimeError(f'host tool version mismatch: {versions}')
        database = output / 'terminfo'
        database.mkdir()
        command = [str(tic), '-x', '-e', 'xterm', '-o', str(database), str(source / 'misc/terminfo.src')]
        result['commands'].append(command)
        with (output / 'tic.log').open('w') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        entry = database / 'x/xterm'
        if not entry.is_file() or entry.is_symlink() or entry.stat().st_size < 12:
            raise RuntimeError('tic did not produce a regular x/xterm entry')
        magic = int.from_bytes(entry.read_bytes()[:2], 'little')
        if magic not in (0x011a, 0x021e):
            raise RuntimeError(f'unsupported compiled terminfo magic: {magic:#x}')
        command = [str(infocmp), '-x', '-A', str(database), 'xterm']
        result['commands'].append(command)
        with (output / 'infocmp.txt').open('w') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        decoded = (output / 'infocmp.txt').read_text()
        if not all(capability in decoded for capability in ('colors#8', 'cup=', 'clear=', 'kcub1=')):
            raise RuntimeError('generated entry lacks required screen/color/left-key capabilities')
        result.update(status='built_guest_not_run', versions=versions,
                      tic_sha256=sha(tic), infocmp_sha256=sha(infocmp),
                      terminfo_source_sha256=sha(source / 'misc/terminfo.src'),
                      entry='x/xterm', entry_sha256=sha(entry), entry_bytes=entry.stat().st_size,
                      entry_magic=magic, infocmp_output_sha256=sha(output / 'infocmp.txt'))
        if (sha(archive) != result['source_sha256'] or sha(LOCK_PATH) != result['source_lock_sha256'] or
            sha(target_report_path) != result['target_report_sha256'] or
            sha(target_config) != result['target_config_sha256'] or sha(target_library) != result['target_library_sha256']):
            raise RuntimeError('source or target probe changed during build')
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
