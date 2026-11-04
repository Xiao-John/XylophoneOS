#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-link ncurses, locale and terminal failure probes; not guest acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    probe, sdk, output = args.probe.resolve(), args.sdk.resolve(), args.output.resolve()
    if output.exists() or any(output.is_relative_to(p) for p in (ROOT / 'src', ROOT / 'localpilot', sdk, probe)):
        raise SystemExit('output must be a new private directory')
    report = json.loads((probe / 'report.json').read_text())
    source_lock = json.loads((ROOT / 'src/ports/ncurses/source_lock.json').read_text())
    sdk_tree, _ = tree_receipt(sdk)
    if (report.get('archive_valid') is not True or not report.get('inputs_unchanged') or
        report.get('sdk_tree_sha256') != sdk_tree or '--disable-sigwinch' not in report['configure_command'] or
        '-D_XOPEN_SOURCE=700' not in report['environment']['CPPFLAGS'] or
        report.get('source_sha256') != source_lock['archive_sha256'] or
        '#define _MB_CAPABLE 1' not in (sdk / 'include/newlib.h').read_text()):
        raise SystemExit('probe did not validate a matching target archive and selected configuration')
    compiler = shutil.which('x86_64-elf-gcc')
    if not compiler or Path(compiler).resolve() != Path(report['target_compiler']).resolve():
        raise SystemExit('target compiler differs from ncurses probe')
    lib = probe / 'build/lib/libncursesw.a'
    if not lib.is_file() or sha(lib) != report.get('archive_sha256'):
        raise SystemExit('target archive differs from the probe report')
    include = probe / 'build/include'
    tools = probe / 'target_tools'
    libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
    output.mkdir(parents=True)
    sources = [ROOT / 'tests/fixtures/ncursesw/wide_screen_probe.c',
               ROOT / 'tests/fixtures/ncursesw/reentry_probe.c',
               ROOT / 'tests/fixtures/ncursesw/wide_locale_probe.c',
               ROOT / 'tests/fixtures/ncursesw/terminal_failure_probe.c',
               ROOT / 'tests/fixtures/ncursesw/terminal_crash_probe.c']
    results = {'status': 'failed', 'guest_run': False, 'sdk_tree_sha256': sdk_tree,
               'probe_report_sha256': sha(probe / 'report.json'), 'ncurses_archive_sha256': sha(lib),
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sources}, 'commands': [], 'artifacts': {}}
    try:
        for source in sources:
            target = output / (source.stem + '.elf')
            command = [compiler, '-B' + str(tools) + '/', '-std=c11', '-O2', '-mno-red-zone',
                       '-fno-pie', '-fno-pic', '-fno-stack-protector', '-D_XOPEN_SOURCE=700',
                       '-D_XOPEN_SOURCE_EXTENDED=1', '-I', str(include), '-isystem', str(sdk / 'include'),
                       '-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                       '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), str(source),
                       '-Wl,--start-group', str(lib), *(str(sdk / 'lib' / name) for name in
                           ('libxos.a', 'libxos_loader.a', 'libc.a', 'libm.a')), libgcc, '-Wl,--end-group',
                       '-o', str(target)]
            results['commands'].append(command)
            with (output / (source.stem + '.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            results['artifacts'][target.name] = sha(target)
        if (tree_receipt(sdk)[0] != sdk_tree or sha(lib) != results['ncurses_archive_sha256'] or
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
