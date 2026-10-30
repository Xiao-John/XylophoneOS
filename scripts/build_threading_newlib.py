# SPDX-License-Identifier: Apache-2.0
"""Build a private newlib 4.6 prefix with real retargetable locks and __getreent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = '6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / '.cache/xos_seed/threading_newlib')
    parser.add_argument('--jobs', type=int, default=8, help='positive parallel build job count (default: 8)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise SystemExit('newlib source archive SHA256 differs from the frozen input')
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=True)
    source = work / 'newlib-4.6.0.20260123'
    if not source.exists():
        with tarfile.open(args.archive) as archive:
            archive.extractall(work, filter='data')
    tools = work / 'target_tools'
    tools.mkdir(exist_ok=True)
    for tool in ['as', 'ld']:
        path = tools / tool
        if not path.exists():
            path.symlink_to(shutil.which('x86_64-elf-' + tool))
    build, prefix = work / 'build', work / 'prefix'
    build.mkdir(exist_ok=True)
    commands = []
    def run(command, log, cwd):
        commands.append([str(x) for x in command])
        with (work / log).open('w') as output:
            subprocess.run(command, check=True, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
    env = os.environ.copy()
    env.pop('COMPILER_PATH', None)
    env.update(CC_FOR_TARGET='x86_64-elf-gcc -B' + str(tools) + '/',
               CCAS_FOR_TARGET='x86_64-elf-gcc -B' + str(tools) + '/',
               CFLAGS_FOR_TARGET='-O2 -g -mno-red-zone -D__DYNAMIC_REENT__')
    run([str(source / 'configure'), '--target=x86_64-elf', '--prefix=' + str(prefix),
         '--disable-multilib', '--disable-newlib-supplied-syscalls', '--disable-libgloss',
         '--enable-newlib-retargetable-locking', '--enable-newlib-global-atexit',
         '--enable-newlib-global-stdio-streams', '--disable-newlib-io-long-double',
         '--disable-newlib-io-long-long', '--disable-newlib-io-c99-formats',
         '--disable-newlib-io-pos-args'], 'configure.log', build)
    run(['make', '-j' + str(args.jobs)], 'make.log', build)
    run(['make', 'install'], 'install.log', build)
    artifacts = {str(p.relative_to(prefix)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in prefix.rglob('*') if p.is_file()}
    (work / 'receipt.json').write_text(json.dumps({'source_sha256': SOURCE_SHA256,
        'commands': commands, 'environment': {k: env[k] for k in ['CC_FOR_TARGET', 'CCAS_FOR_TARGET', 'CFLAGS_FOR_TARGET']},
        'artifacts': artifacts}, indent=2) + '\n')
    print(prefix)
if __name__ == '__main__':
    main()
