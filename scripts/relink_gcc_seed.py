# SPDX-License-Identifier: Apache-2.0
"""Derive a GCC Seed by patching lrealpath and replaying recorded link commands only."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-manifest', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--output-root', type=Path, required=True)
    p.add_argument('--sdk', type=Path, help='Explicit replacement immutable SDK; preserves original wrappers')
    p.add_argument('--gxx', action='store_true', help='Use the delivered E08-5 work layout and relink only g++/cc1plus')
    a = p.parse_args()
    work = a.work.resolve(strict=True)
    out = a.output_root.resolve()
    if ROOT not in out.parents or out == work or work in out.parents:
        p.error('output-root must be a separate XOS workspace directory')
    source = work / 'source/gcc-16.2.0' if a.gxx else ROOT / '.cache/xos_seed/gcc/source/gcc-16.2.0'
    wrapper_root = work / 'bin' if a.gxx else work
    target_tools = (('xg++', 'g++'), ('cc1plus', 'cc1plus')) if a.gxx else (('xgcc', 'gcc'), ('cpp', 'cpp'), ('cc1', 'cc1'))
    original = a.source_manifest.resolve(strict=True)
    seed = json.loads(original.read_text())
    out.mkdir(parents=True, exist_ok=True)
    old_sdk = ROOT / seed['sdk_manifest']['path']
    if old_sdk.name == 'manifest.json':
        old_sdk = old_sdk.parent
    sdk = a.sdk.resolve(strict=True) if a.sdk else old_sdk
    sdk_manifest = sdk / 'manifest.json'
    if ROOT not in sdk.parents or not sdk_manifest.is_file():
        p.error('SDK must have a manifest inside the workspace')
    wrappers = {}
    for name in ('xos-cc', 'xos-cxx'):
        content = (wrapper_root / name).read_text()
        if str(old_sdk) not in content:
            raise ValueError('Original wrapper does not bind the declared SDK')
        destination = out / name
        destination.write_text(content.replace(str(old_sdk), str(sdk)))
        destination.chmod(0o755)
        wrappers[name] = destination
    derived_source = out / 'source/libiberty'
    derived_source.mkdir(parents=True, exist_ok=True)
    (derived_source / 'lrealpath.c').write_bytes((source / 'libiberty/lrealpath.c').read_bytes())
    patch = ROOT / 'src/ports/gcc/patches/0007_libiberty_xos_lrealpath_fallback.patch'
    subprocess.run(['patch', '-p1', '-i', str(patch)], cwd=out / 'source', check=True)
    obj = out / 'lrealpath.o'
    compile_cmd = [str(wrappers['xos-cc']), '-c', '-DHAVE_CONFIG_H', '-O2', '-g0',
                   '-I' + str(work / 'build/libiberty'), '-I' + str(source / 'include'),
                   '-I' + str(source / 'libiberty'), str(derived_source / 'lrealpath.c'), '-o', str(obj)]
    commands = []
    def run(cmd, cwd):
        commands.append({'argv': cmd, 'cwd': str(cwd)})
        subprocess.run(cmd, cwd=cwd, check=True)
    run(compile_cmd, work / 'build/libiberty')
    log_lines = (work / 'build/build3.log' if a.gxx else work / 'build.log').read_text().splitlines()
    links = {}
    wrapper = (wrapper_root / 'xos-cxx').resolve()
    for i, line in enumerate(log_lines):
        if not line.startswith('/') or Path(line.split()[0]).resolve() != wrapper or ' -c ' in line:
            continue
        assembled = line
        while assembled.rstrip().endswith('\\'):
            i += 1
            assembled = assembled.rstrip()[:-1] + ' ' + log_lines[i]
        args = shlex.split(assembled)
        if '-o' not in args:
            continue
        name = args[args.index('-o') + 1]
        if name in dict(target_tools):
            links[name] = args
    missing = {name for name, _ in target_tools} - set(links)
    if missing:
        raise ValueError('No recorded final link command for: ' + repr(missing))
    input_hashes = {str(original.relative_to(ROOT)): sha(original),
                    str(patch.relative_to(ROOT)): sha(patch),
                    str((source / 'libiberty/lrealpath.c').relative_to(ROOT)): sha(source / 'libiberty/lrealpath.c'),
                    str((wrapper_root / 'xos-cc').relative_to(ROOT)): sha(wrapper_root / 'xos-cc'),
                    str((wrapper_root / 'xos-cxx').relative_to(ROOT)): sha(wrapper_root / 'xos-cxx')}
    for path in sorted(sdk.rglob('*')):
        if path.is_symlink():
            raise ValueError('SDK symlinks are not supported')
        if path.is_file():
            input_hashes[str(path.relative_to(ROOT))] = sha(path)
    for path in wrappers.values():
        input_hashes[str(path.relative_to(ROOT))] = sha(path)
    # Bind the actual compiler support library and host C++ closure selected by
    # the wrappers, including headers used to compile the one replacement object.
    import ast
    for wrapper_path in wrappers.values():
        values = {}
        for node in ast.parse(wrapper_path.read_text()).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        values[target.id] = node.value.value
        for key in ('compiler', 'libgcc', 'stdcxx'):
            value = values.get(key)
            if not value:
                continue
            path = Path(value).resolve(strict=True)
            paths = sorted(path.rglob('*')) if path.is_dir() else [path]
            for bound in paths:
                if bound.is_file():
                    input_hashes[str(bound)] = sha(bound)
    changed = {}
    for internal, name in target_tools:
        args = list(links[internal])
        args[0] = str(wrappers['xos-cxx'])
        for arg in args[1:]:
            candidate = Path(arg) if Path(arg).is_absolute() else work / 'build/gcc' / arg
            if candidate.is_file() and (arg.endswith(('.o', '.a'))):
                input_hashes[str(candidate.resolve().relative_to(ROOT))] = sha(candidate)
        destination = out / 'tools' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        args[args.index('-o') + 1] = str(destination)
        args.insert(1, str(obj))
        run(args, work / 'build/gcc')
        old = seed['tools'][name]
        new = {'path': str(destination.relative_to(ROOT)), 'guest_path': old['guest_path'],
               'bytes': destination.stat().st_size, 'sha256': sha(destination)}
        changed[old['sha256']] = new
        seed['tools'][name] = new
    for entry in seed['install_files']:
        if entry['sha256'] in changed:
            new = changed[entry['sha256']]
            entry.update({key: new[key] for key in ('path', 'sha256', 'bytes')})
    seed['sdk_manifest'] = {'path': str(sdk_manifest.relative_to(ROOT)), 'sha256': sha(sdk_manifest)}
    seed['sdk_manifest_sha256'] = sha(sdk_manifest)
    seed['derivation'] = {'kind': 'single_source_fix_and_recorded_links',
                          'not_relinked': ['collect2 (not used by the XOS direct-ld profile)'],
                          'source_manifest': str(original.relative_to(ROOT)),
                          'source_manifest_sha256': sha(original), 'input_hashes': input_hashes,
                          'fixed_object_sha256': sha(obj), 'commands': commands,
                          'note': 'No configure/full GCC recompile. Original link objects are reused; SDK replacement changes static link runtime only. collect2 retains the parent SDK and is not used by the direct-ld profile.'}
    (out / 'seed_manifest.json').write_text(json.dumps(seed, indent=2) + '\n')
    print(out / 'seed_manifest.json')


if __name__ == '__main__':
    main()
