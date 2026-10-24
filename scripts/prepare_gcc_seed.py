# SPDX-License-Identifier: Apache-2.0
"""Prepare explicit XOS installation manifests from separately bound GCC/SDK/binutils inputs."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = '''# SPDX-License-Identifier: Apache-2.0
# XOS static C profile: XOS CRT owns constructors and frame registration.
*cpp:
-isystem /sysroot/include

*cc1:
-mno-red-zone -fno-pie -fno-pic

*link:
-m elf_x86_64 -static -T /sysroot/lib/user.ld -L /sysroot/lib --build-id=none -z noexecstack -z max-page-size=4096

*linker:
/usr/bin/x86_64-elf-ld

*startfile:
/sysroot/lib/crt0_posix.o

*endfile:
%{!nostdlib:}

*lib:
--start-group -lxos -lxos_loader -lc -lm -lgcc --end-group

'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def item(path, guest):
    original = Path(path).absolute()
    if ROOT not in original.parents or original.relative_to(ROOT).parts[0] == 'localpilot':
        raise ValueError('Explicit input must stay inside XOS and outside localpilot')
    for component in (original, *original.parents):
        if component == ROOT:
            break
        if component.is_symlink():
            raise ValueError('Symlink input is not supported: ' + str(component))
    path = original.resolve(strict=True)
    if ROOT not in path.parents or not path.is_file():
        raise ValueError('All explicit inputs must be regular files inside the XOS workspace')
    return {'path': str(path.relative_to(ROOT)), 'guest_path': guest,
            'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gcc-manifest', type=Path, required=True)
    parser.add_argument('--binutils-manifest', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--gxx-manifest', type=Path, help='Optional delivered G++/cc1plus whitelist')
    parser.add_argument('--runtime-manifest', type=Path, help='Target application C++ runtime manifest')
    parser.add_argument('--runtime-prefix', type=Path, help='Explicit target C++ runtime root')
    parser.add_argument('--target-sdk', type=Path, help='Explicit application SDK; tool runtime SDKs remain separately bound')
    args = parser.parse_args()
    out = args.output_root.resolve()
    if ROOT / 'build' not in out.parents:
        parser.error('output-root must be a dedicated directory inside build/')
    out.mkdir(parents=True, exist_ok=True)
    gcc_path = args.gcc_manifest.resolve(strict=True)
    bin_path = args.binutils_manifest.resolve(strict=True)
    gcc, binary = read(gcc_path), read(bin_path)
    cpp = None
    if any((args.gxx_manifest, args.runtime_manifest, args.runtime_prefix)):
        if not all((args.gxx_manifest, args.runtime_manifest, args.runtime_prefix)):
            parser.error('G++ bundle requires all three --gxx-manifest/--runtime-manifest/--runtime-prefix')
        cpp = read(args.gxx_manifest.resolve(strict=True))
    sdk_item = (cpp or gcc)['sdk_manifest']
    sdk_manifest = ROOT / (sdk_item['path'] if isinstance(sdk_item, dict) else sdk_item)
    expected = sdk_item['sha256'] if isinstance(sdk_item, dict) else (cpp or gcc)['sdk_manifest_sha256']
    if sha(sdk_manifest) != expected:
        raise ValueError('GCC SDK manifest changed')
    tool_sdks = {'gcc': gcc['sdk_manifest']}
    if cpp:
        tool_sdks['g++'] = cpp['sdk_manifest']
    if args.target_sdk:
        # Tools remain the exact delivered static binaries. This changes only
        # the explicitly installed SDK for newly compiled applications.
        sdk_manifest = args.target_sdk.resolve(strict=True) / 'manifest.json'
        if ROOT not in sdk_manifest.parents:
            parser.error('target-sdk must be an immutable workspace SDK')
        expected = sha(sdk_manifest)
    seed = {'manifest_schema': 1, 'sdk_manifest': str(sdk_manifest.relative_to(ROOT)),
            'sdk_manifest_sha256': expected, 'tools': dict(gcc['tools']),
            'install_files': list(gcc['install_files']),
            'input_manifests': {str(gcc_path.relative_to(ROOT)): sha(gcc_path),
                                str(bin_path.relative_to(ROOT)): sha(bin_path)},
            'profile': 'static_xos_c_direct_gnu_ld',
            'profile_note': 'XOS CRT handles init/fini/frames; direct ld avoids granting collect2 child construction authority'}
    seed['tool_runtime_sdks'] = tool_sdks
    if cpp:
        for name in ('g++', 'cc1plus'):
            tool = cpp['tools'][name]
            matches = [entry for entry in cpp['install_files']
                       if all(entry.get(key) == tool.get(key) for key in ('path', 'guest_path', 'sha256'))]
            if len(matches) != 1:
                raise ValueError('G++ tool must have one exact install mapping: ' + name)
            entry = item(ROOT / tool['path'], tool['guest_path'])
            if entry['sha256'] != tool['sha256']:
                raise ValueError('G++ tool changed: ' + name)
            seed['tools'][name] = entry
            seed['install_files'].append(entry)
        seed['input_manifests'][str(args.gxx_manifest.resolve().relative_to(ROOT))] = sha(args.gxx_manifest)
    for name in ('as', 'ld', 'ar', 'ranlib', 'strip', 'nm'):
        original = binary['tools'][name]
        source = bin_path.parent / 'install' / original['path']
        if sha(source) != original['sha256']:
            raise ValueError('Binutils tool changed: ' + name)
        entry = item(source, '/usr/bin/x86_64-elf-' + name)
        seed['install_files'].append(entry)
        seed['tools'][name] = dict(entry)
        if name == 'as':
            # GCC's built-in assembler spec invokes the native host name "as".
            # Install an explicit byte-identical alias; XOS has no symlinks.
            seed['install_files'].append(item(source, '/usr/bin/as'))
    sdk = sdk_manifest.parent
    cpp_files = []
    specs_text = SPECS
    if cpp:
        from cpp_seed_bundle import bind_runtime, cpp_specs
        cpp_files, includes, archives = bind_runtime(args.runtime_manifest,
                                                    args.runtime_prefix.resolve(strict=True), sdk, item)
        specs_text = cpp_specs(SPECS, includes, archives)
        seed['profile'] = 'static_xos_cpp_direct_gnu_ld'
        seed['target_runtime_manifest'] = str(args.runtime_manifest.resolve().relative_to(ROOT))
        seed['target_runtime_manifest_sha256'] = sha(args.runtime_manifest)
        seed['input_manifests'][seed['target_runtime_manifest']] = sha(args.runtime_manifest)
    specs = out / 'specs'
    specs.write_text(specs_text)
    seed['install_files'].append(item(specs, '/usr/lib/gcc/x86_64-elf/16.2.0/specs'))
    files = []
    for path in sorted((sdk / 'include').rglob('*')):
        if path.is_symlink():
            raise ValueError('Symlink in SDK include closure: ' + str(path))
        if path.is_file():
            files.append(item(path, '/sysroot/include/' + path.relative_to(sdk / 'include').as_posix()))
    for name in ('crt0_posix.o', 'user.ld', 'lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a'):
        guest = '/sysroot/lib/' + Path(name).name
        files.append(item(sdk / name, guest))
    files.extend(cpp_files)
    sysroot = {'manifest_schema': 1, 'kind': 'target_xos_cpp' if cpp else 'target_xos_c', 'files': files,
               'sdk_manifest_sha256': expected, 'guest_root': '/sysroot'}
    # Root-relative paths are explicit, even when inputs originate in different caches.
    (out / 'seed_manifest.json').write_text(json.dumps(seed, indent=2) + '\n')
    (out / 'sysroot_manifest.json').write_text(json.dumps(sysroot, indent=2) + '\n')
    print(json.dumps({'seed_manifest': str(out / 'seed_manifest.json'),
                      'sysroot_manifest': str(out / 'sysroot_manifest.json'),
                      'seed_root': str(ROOT), 'sysroot_root': str(ROOT),
                      'files': len(seed['install_files']) + len(files)}, indent=2))


if __name__ == '__main__':
    main()
