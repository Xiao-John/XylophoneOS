# SPDX-License-Identifier: Apache-2.0
"""Derive the delivered static target runtime for a libc-provided TLS exit ABI."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hash(path):
    value = hashlib.sha256()
    for entry in sorted(path.rglob('*')):
        if entry.is_symlink():
            raise ValueError('Runtime input cannot contain symlinks')
        if entry.is_file():
            value.update(entry.relative_to(path).as_posix().encode())
            value.update(b'\0')
            value.update(bytes.fromhex(sha(entry)))
    return value.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--sdk', type=Path, required=True)
    p.add_argument('--output-root', type=Path, required=True)
    p.add_argument('--frontend-manifest', type=Path, help='Bind separately delivered libsupc++ hash when absent in runtime manifest')
    a = p.parse_args()
    prefix, sdk, out = a.prefix.resolve(strict=True), a.sdk.resolve(strict=True), a.output_root.resolve()
    if ROOT not in out.parents or out.exists() or prefix in out.parents or sdk in out.parents:
        p.error('output must be a new separate directory within XOS')
    if out.relative_to(ROOT).parts[0] == 'localpilot':
        p.error('localpilot is not an XOS output')
    manifest = json.loads(a.manifest.read_text())
    commands = []
    ar = shutil.which('x86_64-elf-ar')
    nm = shutil.which('x86_64-elf-nm')
    if not ar or not nm:
        p.error('Target GNU ar/nm required')
    symbols = subprocess.check_output([nm, '-g', '--defined-only', str(sdk/'lib/libxos.a')], text=True)
    if ' T __cxa_thread_atexit\n' not in symbols:
        raise ValueError('Application SDK must actually provide the TLS exit entry')
    for entry in manifest['include_dirs']:
        if entry['root'] == 'runtime' and tree_hash(prefix/entry['path']) != entry['sha256']:
            raise ValueError('Original runtime headers changed')
    for entry in manifest['archives']:
        if entry['root'] == 'runtime' and sha(prefix/entry['path']) != entry['sha256']:
            raise ValueError('Original runtime archive changed')
    manifest['provenance']['library_build_sdk'] = manifest['sdk_manifest']
    manifest['provenance']['original_link_inputs'] = [dict(entry) for entry in manifest['archives']]
    manifest['sdk_manifest'] = {'path': 'manifest.json', 'sha256': sha(sdk/'manifest.json')}
    for entry in manifest['archives']:
        entry['role'] = Path(entry['path']).stem
        if entry['root'] == 'sdk':
            entry['sha256'] = sha(sdk/entry['path'])
    if not any(entry['role'] == 'libsupc++' for entry in manifest['archives']):
        if not a.frontend_manifest:
            p.error('Missing libsupc++ declaration; provide frontend-manifest')
        frontend = json.loads(a.frontend_manifest.read_text())
        digest = sha(prefix/'lib/libsupc++.a')
        if digest != frontend['target_runtime']['libsupc++.a']:
            raise ValueError('Separately delivered libsupc++ differs from frontend receipt')
        manifest['archives'].append({'root': 'runtime', 'path': 'lib/libsupc++.a',
                                     'role': 'libsupc++', 'sha256': digest})
    manifest['compile_flags'] += [flag for flag in ('-ftls-model=local-exec', '-fuse-cxa-atexit')
                                  if flag not in manifest['compile_flags']]
    out.mkdir(parents=True)
    shutil.copytree(prefix/'include', out/'include')
    (out/'lib').mkdir()
    inputs = {}
    for name in ('libstdc++.a', 'libsupc++.a', 'libgcc.a'):
        source = prefix/'lib'/name
        inputs[str(source.relative_to(ROOT))] = sha(source)
        shutil.copyfile(source, out/'lib'/name)
        if name != 'libgcc.a':
            members = subprocess.check_output([ar, 't', str(source)], text=True).splitlines()
            if members.count('atexit_thread.o') != 1:
                raise ValueError('Expected exactly one GNU TLS fallback member in '+name)
            cmd = [ar, 'd', str(out/'lib'/name), 'atexit_thread.o']
            subprocess.run(cmd, check=True); commands.append(cmd)
            cmd = [ar, 'sD', str(out/'lib'/name)]
            subprocess.run(cmd, check=True); commands.append(cmd)
    config = out/'include/c++/16.2.0/x86_64-unknown-elf/bits/c++config.h'
    old = '/* #undef _GLIBCXX_HAVE___CXA_THREAD_ATEXIT */'
    text = config.read_text()
    if text.count(old) != 1:
        raise ValueError('Unexpected target runtime configuration')
    config.write_text(text.replace(old, '#define _GLIBCXX_HAVE___CXA_THREAD_ATEXIT 1'))
    manifest['provenance']['original_runtime_inputs'] = inputs
    manifest['provenance']['tls_exit_adaptation'] = {
        'reason': 'SDK provides the entry; GNU atexit_thread.cc selects an empty implementation with this configuration',
        'removed_member': 'atexit_thread.o', 'config_macro': '_GLIBCXX_HAVE___CXA_THREAD_ATEXIT=1',
        'commands': commands, 'ar_sha256': sha(Path(ar).resolve()),
        'source_manifest_sha256': sha(a.manifest), 'source_manifest': str(a.manifest)}
    for entry in manifest['include_dirs']:
        base = out if entry['root'] == 'runtime' else sdk
        entry['sha256'] = tree_hash(base/entry['path'])
    for entry in manifest['archives']:
        if entry['root'] == 'runtime':entry['sha256'] = sha(out/entry['path'])
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(out/'manifest.json')


if __name__ == '__main__':
    main()
