# SPDX-License-Identifier: Apache-2.0
"""Bind a delivered target C++ runtime to explicit XOS install files and GCC specs."""
from pathlib import Path
import json

from build_cpp_abi_probe import resolve_artifact, checked_hash, reject_symlink_components

FEATURES = ('string_vector', 'exceptions', 'rtti', 'local_static', 'tls_destructors', 'multi_tu')


def bind_runtime(manifest_path, runtime_root, sdk_root, make_item):
    """Return only declared and hash-verified inputs; never discover a host library."""
    data = json.loads(Path(manifest_path).read_text())
    if data.get('runtime_kind') != 'target_application_runtime':
        raise ValueError('G++ bundle requires target_application_runtime, not compiler host libraries')
    if data.get('target_triple') != 'x86_64-elf':
        raise ValueError('Target runtime must generate XOS x86_64-elf code')
    flags = data.get('runtime_build_flags', []) + data.get('host_library_build_flags', [])
    if any(flag in ('-fno-exceptions', '-fno-rtti') for flag in flags):
        raise ValueError('E08-5 target runtime must retain exceptions and RTTI')
    for feature in FEATURES:
        if data.get('features', {}).get(feature, {}).get('status') != 'ready':
            raise ValueError('Target runtime has not declared feature ready: ' + feature)
    binding = data.get('sdk_manifest', {})
    relative = Path(binding.get('path', ''))
    if not relative.parts or relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Runtime must bind a relative SDK manifest')
    reject_symlink_components(sdk_root / relative, 'runtime SDK manifest')
    checked_hash(sdk_root / relative, binding.get('sha256', ''), 'runtime SDK manifest')
    # Also bind the CRT/script, even though the common sysroot installs them.
    for name, expected in (('crt', sdk_root / 'crt0_posix.o'),
                           ('linker_script', sdk_root / 'user.ld')):
        path, _ = resolve_artifact(data.get(name), sdk_root, runtime_root, name)
        if path != expected:
            raise ValueError('Runtime must bind the XOS profile ' + name)
    files, includes = [], []
    for index, entry in enumerate(data.get('include_dirs', [])):
        path, _ = resolve_artifact(entry, sdk_root, runtime_root, 'C++ include directory')
        if not path.is_dir():
            raise ValueError('C++ include input must be a directory')
        # C headers already have a canonical position; add them after C++ below.
        if path == sdk_root / 'include':
            continue
        guest = '/sysroot/cxx_include/' + str(index)
        includes.append(guest)
        for source in sorted(path.rglob('*')):
            if source.is_file():
                files.append(make_item(source, guest + '/' + source.relative_to(path).as_posix()))
    if not includes:
        raise ValueError('Target runtime must declare its C++ include directories')
    archives = {}
    for entry in data.get('archives', []):
        path, _ = resolve_artifact(entry, sdk_root, runtime_root, 'C++ runtime archive')
        if not path.is_file() or path.suffix != '.a':
            raise ValueError('Runtime archives must be regular static .a files')
        role = entry.get('role')
        # SDK libraries are already installed with the SDK, with their own hashes.
        if entry.get('root') == 'sdk':
            if path.parent != sdk_root / 'lib':
                raise ValueError('Unexpected SDK archive location')
            continue
        names = {'libstdc++': 'libstdc++.a', 'libsupc++': 'libsupc++.a', 'libgcc': 'libgcc.a',
                 'libgcc_eh': 'libgcc_eh.a'}
        if role not in names or role in archives:
            raise ValueError('Unknown or duplicate target runtime archive role: ' + str(role))
        archives[role] = names[role]
        files.append(make_item(path, '/sysroot/lib/' + names[role]))
    if not {'libstdc++', 'libsupc++', 'libgcc'} <= archives.keys():
        raise ValueError('Target runtime must bind libstdc++, libsupc++ and actual libgcc archives')
    return files, includes, archives


def cpp_specs(c_specs, include_paths, archives):
    # Put C++ wrappers before C headers so their #include_next directives work.
    common = '-mno-red-zone -fno-pie -fno-pic -ftls-model=local-exec'
    cxx = ' '.join('-isystem ' + path for path in include_paths)
    # cc1_options (%1) is also used by cc1plus; a C -isystem there would
    # precede the C++ wrappers despite their later %2 flags. -idirafter puts
    # C headers after all system directories for both frontends.
    specs = c_specs.replace('*cpp:\n-isystem /sysroot/include', '*cpp:\n%{!nostdinc:}')
    specs = specs.replace('*cc1:\n-mno-red-zone -fno-pie -fno-pic',
                          '*cc1:\n-idirafter /sysroot/include ' + common)
    specs += '*cc1plus:\n' + cxx + ' ' + common + '\n\n'
    libraries = '-lstdc++ -lsupc++ '
    if 'libgcc_eh' in archives:
        libraries += '-lgcc_eh '
    return specs.replace('--start-group -lxos', '--start-group ' + libraries + '-lxos')
