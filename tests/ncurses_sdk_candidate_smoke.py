# SPDX-License-Identifier: Apache-2.0
"""Link independent consumers using only the composed candidate SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or any(output.is_relative_to(p) for p in (candidate, ROOT / 'src', ROOT / 'localpilot')):
        raise SystemExit('output must be a new private directory')
    receipt = json.loads((candidate / 'receipt.json').read_text())
    files = {p.relative_to(candidate).as_posix(): sha(p) for p in sorted(candidate.rglob('*'))
             if p.is_file() and p != candidate / 'receipt.json'}
    digest = hashlib.sha256((json.dumps(files, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()).hexdigest()
    if receipt.get('status') != 'built_unverified' or files != receipt['files'] or digest != receipt.get('tree_sha256'):
        raise SystemExit('candidate files differ from receipt')
    for path in candidate.rglob('*'):
        if path.is_symlink():
            raise SystemExit('candidate contains a symlink')
    cc, assembler, linker = (shutil.which(name) for name in
                              ('x86_64-elf-gcc', 'x86_64-elf-as', 'x86_64-elf-ld'))
    if not all((cc, assembler, linker)):
        raise SystemExit('target compiler or binutils missing')
    sdk = candidate / 'sdk'
    libgcc = subprocess.check_output([cc, '-print-libgcc-file-name'], text=True).strip()
    output.mkdir(parents=True)
    names = ('wide_screen_probe', 'reentry_probe', 'wide_locale_probe', 'terminal_failure_probe',
             'terminal_crash_probe')
    sources = [ROOT / 'tests/fixtures/ncursesw' / (name + '.c') for name in names]
    results = {'status': 'failed', 'candidate_tree_sha256': receipt['tree_sha256'], 'artifacts': {},
               'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sources}}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_ncurses_sdk_tools_') as folder:
            tools = Path(folder)
            (tools / 'as').symlink_to(Path(assembler).resolve())
            (tools / 'ld').symlink_to(Path(linker).resolve())
            for name, source in zip(names, sources):
                target = output / (name + '.elf')
                command = [cc, '-B' + str(tools) + '/', '-std=c11', '-O2', '-mno-red-zone',
                           '-fno-pie', '-fno-pic', '-fno-stack-protector', '-D_XOPEN_SOURCE=700',
                           '-D_XOPEN_SOURCE_EXTENDED=1', '-I', str(sdk / 'include/ncursesw'),
                           '-isystem', str(sdk / 'include'), '-nostdlib', '-static', '-no-pie',
                           '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                           '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), str(source),
                           '-Wl,--start-group', *(str(sdk / 'lib' / lib) for lib in
                             ('libncursesw.a', 'libxos.a', 'libxos_loader.a', 'libc.a', 'libm.a')),
                           libgcc, '-Wl,--end-group', '-o', str(target)]
                subprocess.run(command, check=True)
                results['artifacts'][target.name] = sha(target)
        if any(sha(p) != results['source_sha256'][str(p.relative_to(ROOT))] for p in sources):
            raise RuntimeError('consumer source changed during linking')
        results['status'] = 'cross_linked_guest_not_run'
    finally:
        (output / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
