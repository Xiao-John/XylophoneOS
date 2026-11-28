#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the explicit terminal test supervisor from an anchored approved launcher."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from sdk_receipt import verify_sdk
from shell_launch_support import bind_system, relative_file, sha
from toolchain import audit, tool
from xypm_sdk_profile import inspect_sdk


def native_payload(sdk):
    """Every header and native link input used by this freestanding fixture."""
    names = ['crt0.o', 'user.ld', 'lib/libxos.a', 'lib/libxos_loader.a']
    names += [p.relative_to(sdk).as_posix() for p in sorted((sdk / 'include').rglob('*')) if p.is_file()]
    return {name: sha(relative_file(sdk, name)) for name in names}


def payload_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def runtime_layout(path):
    """All loaded bytes/layout and allocated metadata, independent of symbols."""
    data = Path(path).read_bytes()
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('terminal fixture must be a little-endian ELF64 image')
    def bounded(offset, size):
        if offset > len(data) or size > len(data) - offset:
            raise ValueError('terminal fixture ELF range is outside its image')
        return data[offset:offset + size]
    phoff, shoff = struct.unpack_from('<QQ', data, 32)
    phsize, phnum, shsize, shnum, shstrings = struct.unpack_from('<5H', data, 54)
    if phsize != 56 or shsize != 64 or not 0 < phnum <= 32 or not 0 < shnum <= 128 or shstrings >= shnum:
        raise ValueError('terminal fixture ELF table bounds differ')
    headers = bounded(phoff, phsize * phnum)
    loadable = []
    for i in range(phnum):
        values = struct.unpack_from('<II6Q', headers, i * phsize)
        kind, flags, offset, address, physical, size, memory, alignment = values
        if kind == 1:
            loadable.append({'flags': flags, 'offset': offset, 'address': address, 'physical': physical,
                'bytes': size, 'memory_bytes': memory, 'alignment': alignment,
                'sha256': hashlib.sha256(bounded(offset, size)).hexdigest()})
    table = bounded(shoff, shsize * shnum)
    sections = [struct.unpack_from('<II4QII2Q', table, i * shsize) for i in range(shnum)]
    names = bounded(sections[shstrings][4], sections[shstrings][5])
    allocated = []
    for name, kind, flags, address, offset, size, link, info, alignment, entry_bytes in sections:
        if not flags & 2:
            continue
        if name >= len(names) or b'\0' not in names[name:]:
            raise ValueError('allocated terminal fixture section has no bounded name')
        name = names[name:names.index(b'\0', name)].decode('ascii')
        allocated.append({'name': name, 'type': kind, 'flags': flags, 'address': address, 'bytes': size,
            'alignment': alignment, 'entry_bytes': entry_bytes,
            'sha256': None if kind == 8 else hashlib.sha256(bounded(offset, size)).hexdigest()})
    marker = [item for item in allocated if item['name'] == '.xos.exec']
    expected_marker = hashlib.sha256(struct.pack('<QII', 0x3349424143455858, 3, 16)).hexdigest()
    if len(marker) != 1 or marker[0]['bytes'] != 16 or marker[0]['sha256'] != expected_marker:
        raise ValueError('terminal observer descriptor startup marker differs')
    return {'identity_and_entry': data[16:32].hex(), 'program_headers_sha256': hashlib.sha256(headers).hexdigest(),
            'loadable_segments': loadable, 'allocated_sections': allocated}


def bind_supervisor(directory, root=ROOT):
    directory = Path(directory).resolve(strict=True)
    receipt = directory / 'receipt.json'
    report = json.loads(receipt.read_bytes())
    if report.get('status') != 'built_not_run' or report.get('scope') != 'explicit_dynamic_terminal_supervisor_v1':
        raise ValueError('a completed explicit terminal supervisor build is required')
    for name, expected in report['inputs'].items():
        if sha(relative_file(root, name)) != expected:
            raise ValueError('terminal supervisor input differs: ' + name)
    binary = directory / 'terminal-supervisor.elf'
    if set(report['artifacts']) != {binary.name, 'dynamic_roots.hpp'}:
        raise ValueError('unexpected terminal supervisor artifact inventory')
    for name, expected in report['artifacts'].items():
        if sha(relative_file(directory, name)) != expected:
            raise ValueError('terminal supervisor artifact differs: ' + name)
    if payload_digest(report['native_payload']) != report['native_payload_sha256']:
        raise ValueError('terminal native compilation payload digest differs')
    metadata = {'version': 1, 'receipt_sha256': sha(receipt), 'elf_sha256': sha(binary),
                'base_system_build_id': report['base_system_build_id'],
                'base_system_manifest_sha256': report['base_system_manifest_sha256'],
                'base_native_sdk_binding': report['base_native_sdk_binding'],
                'native_payload_sha256': report['native_payload_sha256'],
                'native_payload_files': len(report['native_payload']),
                'approved_generation': report['approved_generation'], 'guest_qualification': 'not_run'}
    return binary, metadata, report


def verify_native_payload(report, sdk):
    current = native_payload(Path(sdk))
    if current != report['native_payload']:
        changed = sorted(set(current) ^ set(report['native_payload']))
        changed += [name for name in current if name in report['native_payload']
                    and current[name] != report['native_payload'][name]]
        raise ValueError('test kernel native compilation inputs differ: ' + ', '.join(changed[:8]))
    return payload_digest(current)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'launcher-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system, launcher = (p.resolve(strict=True) for p in (args.system, args.launcher_build))
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'explicit_dynamic_terminal_supervisor_v1',
              'guest_qualification': 'not_run', 'inputs': {}, 'commands': []}
    inputs = report['inputs']

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        name = path.relative_to(ROOT).as_posix()
        value = sha(path)
        if expected is not None and value != expected:
            raise ValueError('input digest differs: ' + name)
        if name in inputs and inputs[name] != value:
            raise ValueError('input changed: ' + name)
        inputs[name] = value
        return value

    def run(name, command):
        report['commands'].append(list(map(str, command)))
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        base = bind_system(system, ROOT)
        base_receipt = verify_sdk(system / 'sdk', base)
        base_hash = bind(system / 'manifest.json')
        for name, value in base['sources'].items():
            bind(ROOT / name, value)
        for name, value in base['artifacts'].items():
            bind(relative_file(system, name), value['sha256'])
        bind(launcher / 'receipt.json')
        selected = json.loads((launcher / 'receipt.json').read_bytes())
        if (selected.get('status') != 'built_not_run' or len(selected.get('approved_generations', [])) != 1
                or selected['native_system_build_id'] != base['build_id']
                or selected['native_system_manifest_sha256'] != base_hash
                or selected['native_sdk_binding'] != base_receipt):
            raise ValueError('one approved generation bound to the exact producer system is required')
        for name, value in selected['sources'].items():
            bind(ROOT / name, value)
        for name, value in selected['artifacts'].items():
            bind(relative_file(launcher, name), value)
        native = launcher / 'native_sdk_snapshot'
        if verify_sdk(native, base) != base_receipt:
            raise ValueError('approved controller native SDK differs')
        c_binding = inspect_sdk('glibc', launcher / 'sdk_snapshot')['binding']
        if (c_binding != selected['c_sdk_binding'] or c_binding['sdk_manifest_sha256'] != selected['sdk_manifest_sha256']
                or c_binding['sdk_tree_sha256'] != selected['sdk_tree_sha256']):
            raise ValueError('approved controller C SDK anchors differ')
        for sdk in (native, launcher / 'sdk_snapshot'):
            for path in sorted(sdk.rglob('*')):
                if path.is_file(): bind(path)
        generation = selected['approved_generations'][0]
        bind(relative_file(launcher, generation['snapshot']), generation['sha256'])
        payload = native_payload(native)
        shutil.copyfile(launcher / 'dynamic_roots.hpp', out / 'dynamic_roots.hpp')
        source = ROOT / 'tests/fixtures/dynamic_terminal_supervisor.cpp'
        control = ROOT / 'src/user/services/terminal_control.cpp'
        for path in (Path(__file__), source, control,
                     source.parent / 'dynamic_terminal_owner_probe.hpp',
                     source.parent / 'public_runtime/terminal_owner_evidence.h'):
            bind(path)
        binary = out / 'terminal-supervisor.elf'
        run('supervisor', [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
            '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
            '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-unwind-tables',
            '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
            '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++', '-I', str(native / 'include'), '-I', str(out),
            str(source), str(control), '-nostdlib', '-static', '-no-pie',
            '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
            '-T', str(native / 'user.ld'), str(native / 'crt0.o'), '-Wl,--start-group',
            str(native / 'lib/libxos.a'), str(native / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)])
        linked_sha256 = sha(binary)
        loaded = runtime_layout(binary)
        run('strip', [tool('objcopy'), '--strip-all', str(binary)])
        if runtime_layout(binary) != loaded:
            raise ValueError('symbol stripping changed the terminal fixture runtime image')
        if binary.stat().st_size > 131072:
            raise ValueError('terminal supervisor exceeds bootstrap image bound')
        for name, expected in inputs.items():
            if sha(relative_file(ROOT, name)) != expected:
                raise ValueError('input changed during terminal supervisor build: ' + name)
        if bind_system(system, ROOT) != base or verify_sdk(native, base) != base_receipt or native_payload(native) != payload:
            raise ValueError('producer system/native SDK changed during build')
        report.update(status='built_not_run', base_system_build_id=base['build_id'],
            base_system_manifest_sha256=base_hash, base_native_sdk_binding=base_receipt,
            approved_generation=generation, native_payload=payload, native_payload_sha256=payload_digest(payload),
            linked_image_sha256=linked_sha256, symbol_stripping='nonallocated_symbols_only',
            loaded_image_layout=loaded, loaded_image_layout_sha256=payload_digest(loaded),
            artifacts={binary.name: sha(binary), 'dynamic_roots.hpp': sha(out / 'dynamic_roots.hpp')}, toolchain=audit())
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Built explicit dynamic terminal supervisor; guest not run')


if __name__ == '__main__':
    main()
