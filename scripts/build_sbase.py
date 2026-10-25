# SPDX-License-Identifier: Apache-2.0
"""Build the pinned, narrow sbase tool subset for XOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/sbase'
TOOLS = ('cat', 'cp', 'mkdir', 'mv', 'rm')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT/'.cache/xos_seed/sbase/repo')
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    source = args.source.resolve(strict=True)
    lock = json.loads((PORT/'source_lock.json').read_text())
    for name, expected in lock['files'].items():
        path = source/name
        if not path.is_file() or sha(path) != expected:
            parser.error(f'sbase source mismatch: {name}')
    inputs = {str(path.relative_to(ROOT)): sha(path) for path in sorted(PORT.rglob('*')) if path.is_file()}
    inputs['scripts/build_sbase.py'] = sha(__file__)
    inputs.update({'sdk/'+str(path.relative_to(sdk)): sha(path) for path in sorted(sdk.rglob('*')) if path.is_file()})
    key = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    output = ROOT/'.cache/xos_seed/sbase'/key
    output.mkdir(parents=True, exist_ok=True)
    compiler = os.environ.get('XOS_CC', shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc')
    libgcc = subprocess.check_output([compiler, '-print-libgcc-file-name'], text=True).strip()
    built = {}
    for name in TOOLS:
        target = output/name
        command = [compiler, '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic',
                   '-fno-stack-protector', '-idirafter', str(sdk/'include'), '-nostdlib',
                   '-static', '-no-pie', '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
                   '-T', str(sdk/'user.ld'), str(sdk/'crt0_posix.o'),
                   str(PORT/'xos'/(name+'.c')), '-Wl,--start-group',
                   str(sdk/'lib/libxos.a'), str(sdk/'lib/libxos_loader.a'),
                   str(sdk/'lib/libc.a'), str(sdk/'lib/libm.a'), libgcc,
                   '-Wl,--end-group', '-o', str(target)]
        subprocess.run(command, check=True)
        built[name] = {'path': str(target.relative_to(ROOT)), 'guest_path': '/usr/bin/'+name,
                       'sha256': sha(target), 'bytes': target.stat().st_size}
    manifest = {'profile': 'sbase_xos_b1', 'commit': lock['commit'], 'tree': lock['tree'],
                'tools': built, 'inputs': inputs, 'status': 'built_not_run'}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({key:value for key,value in manifest.items() if key!='inputs'}))

if __name__ == '__main__':
    main()
