#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-link ncurses, locale and terminal failure probes; not guest acceptance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from xos_app import tree_receipt
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment
from probe_ncursesw import glibc_inputs

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--glibc-profile', type=Path, help='use the verified glibc sysroot supplied by --sdk')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    probe, sdk, output = args.probe.resolve(), args.sdk.resolve(), args.output.resolve()
    if output.exists() or any(output.is_relative_to(p) for p in (ROOT / 'src', ROOT / 'localpilot', sdk, probe)):
        raise SystemExit('output must be a new private directory')
    report = json.loads((probe / 'report.json').read_text())
    source_lock = json.loads((ROOT / 'src/ports/ncurses/source_lock.json').read_text())
    compiler = shutil.which('x86_64-elf-gcc')
    if not compiler or Path(compiler).resolve() != Path(report['target_compiler']).resolve():
        raise SystemExit('target compiler differs from ncurses probe')
    runtime = 'glibc' if args.glibc_profile else 'newlib'
    if report.get('runtime_family', 'newlib') != runtime:
        raise SystemExit('consumer SDK runtime differs from ncurses probe')
    if args.glibc_profile:
        target_tools = {name: shutil.which('x86_64-elf-' + name) for name in ('gcc', 'as', 'ld', 'ar', 'ranlib')}
        if not all(target_tools.values()):
            raise SystemExit('glibc SDK compiler and binutils are required')
        binding, tools_hash, _, _, target_flags, headers, startup, libraries = glibc_inputs(
            sdk, args.glibc_profile, target_tools)
        sdk_tree = binding['sdk_tree_sha256']
        profile_sha = sha(args.glibc_profile)
        libc_matches = report.get('sdk_profile_sha256') == profile_sha and report.get('target_tools') == tools_hash
        as_ld = [Path(target_tools[name]).resolve() for name in ('as', 'ld')]
        if [(probe / 'target_tools' / name).resolve(strict=True) for name in ('as', 'ld')] != as_ld:
            raise SystemExit('ncurses probe binutils links differ from the verified glibc tools')
        env = clean_build_environment(os.environ)[0]
    else:
        sdk_tree, _ = tree_receipt(sdk)
        libc_matches = '#define _MB_CAPABLE 1' in (sdk / 'include/newlib.h').read_text()
        target_flags, headers = [], ['-isystem', str(sdk / 'include')]
        startup = [str(sdk / 'crt0_posix.o')]
        libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
        libraries = ['-Wl,--start-group', *(str(sdk / 'lib' / name) for name in
                     ('libxos.a', 'libxos_loader.a', 'libc.a', 'libm.a')), libgcc, '-Wl,--end-group']
        env = None
    if (report.get('archive_valid') is not True or not report.get('inputs_unchanged') or
        report.get('sdk_tree_sha256') != sdk_tree or '--disable-sigwinch' not in report['configure_command'] or
        '-D_XOPEN_SOURCE=700' not in report['environment']['CPPFLAGS'] or
        report.get('source_sha256') != source_lock['sha256'] or not libc_matches):
        raise SystemExit('probe did not validate a matching target archive and selected configuration')
    lib = probe / 'build/lib/libncursesw.a'
    if not lib.is_file() or sha(lib) != report.get('archive_sha256'):
        raise SystemExit('target archive differs from the probe report')
    include = probe / 'build/include'
    tools = probe / 'target_tools'
    output.mkdir(parents=True)
    sources = [ROOT / 'tests/fixtures/ncursesw/wide_screen_probe.c',
               ROOT / 'tests/fixtures/ncursesw/reentry_probe.c',
               ROOT / 'tests/fixtures/ncursesw/wide_locale_probe.c',
               ROOT / 'tests/fixtures/ncursesw/terminal_failure_probe.c',
               ROOT / 'tests/fixtures/ncursesw/terminal_crash_probe.c']
    results = {'status': 'failed', 'guest_run': False, 'runtime_family': runtime, 'sdk_tree_sha256': sdk_tree,
               'probe_report_sha256': sha(probe / 'report.json'), 'ncurses_archive_sha256': sha(lib),
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sources}, 'commands': [], 'artifacts': {}}
    try:
        # Keep ncurses inside the existing static archive group with libc.
        libraries = [libraries[0], str(lib), *libraries[1:]]
        for source in sources:
            target = output / (source.stem + '.elf')
            command = [compiler, '-B' + str(tools) + '/', '-std=c11', '-O2', '-mno-red-zone',
                       '-fno-pie', '-fno-pic', '-fno-stack-protector', '-D_XOPEN_SOURCE=700',
                       '-D_XOPEN_SOURCE_EXTENDED=1', *target_flags, '-I', str(include), *headers,
                       '-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                       '-T', str(sdk / 'user.ld'), *startup, str(source), *libraries,
                       '-o', str(target)]
            results['commands'].append(command)
            with (output / (source.stem + '.log')).open('w') as log:
                subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            if args.glibc_profile:
                verify_elf(target)
            results['artifacts'][target.name] = sha(target)
        if args.glibc_profile:
            sdk_unchanged = sha(args.glibc_profile) == profile_sha and glibc_inputs(
                sdk, args.glibc_profile, target_tools)[:2] == (binding, tools_hash)
        else:
            sdk_unchanged = tree_receipt(sdk)[0] == sdk_tree
        if (not sdk_unchanged or sha(lib) != results['ncurses_archive_sha256'] or
            any(sha(p) != results['source_sha256'][str(p.relative_to(ROOT))] for p in sources)):
            raise RuntimeError('SDK or ncurses archive changed during linking')
        results['status'] = 'cross_linked_guest_not_run'
    except Exception as error:
        results['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
