#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a native approved-root controller against externally anchored C SDK bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from archive_member_map import verify_bundle
from sdk_receipt import verify_sdk
from shell_launch_support import bind_system
from toolchain import audit, tool
from xypm_sdk_profile import inspect_sdk

INPUTS = ('scripts/build_dynamic_launcher.py', 'src/user/tools/dynamic_run.cpp',
          'src/user/loader/dynamic/generation.cpp', 'src/user/loader/dynamic/identity.cpp',
          'scripts/xypm_sdk_profile.py', 'scripts/xos_app.py', 'scripts/sdk_receipt.py',
          'scripts/xypm_format.py', 'scripts/toolchain.py', 'scripts/archive_member_map.py',
          'tests/shell_launch_support.py')
VALIDATOR = r'''
#include <xos/dynamic.hpp>
#include <xos/fault_sha256.hpp>
#include <cstdio>
#include <cstring>
using namespace xos;
struct input { u8 bytes[sizeof(dynamic::generation)]; u32 size; };
bool read(void* raw,u64 offset,u8* output,u32 size) {
    auto& in=*static_cast<input*>(raw);
    if(offset>in.size || size>in.size-offset)return false;
    for(u32 i=0;i<size;++i) { output[i]=in.bytes[offset+i]; }
    return true;
}
int main(int argc,char** argv) {
    if(argc!=3 || std::strlen(argv[2])!=64)return 2;
    input in{};auto* stream=std::fopen(argv[1],"rb");if(!stream)return 2;
    in.size=static_cast<u32>(std::fread(in.bytes,1,sizeof(in.bytes),stream));
    const bool excess=std::fgetc(stream)!=EOF;std::fclose(stream);
    if(excess || in.size<sizeof(dynamic::generation_header))return 2;
    u8 sdk[32]{};
    for(u32 i=0;i<64;++i) {
        const char c=argv[2][i];if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return 2;
        sdk[i/2]=static_cast<u8>((sdk[i/2]<<4)|(c<='9'?c-'0':c-'a'+10));
    }
    dynamic::generation_header header{};std::memcpy(&header,in.bytes,sizeof(header));
    dynamic::generation_root root{header.id,{}};sha256 hash;hash.update(in.bytes,in.size);hash.finish(root.sha256);
    dynamic::generation result{};
    const auto error=dynamic::read_generation(read,&in,in.size,root,sdk,result);
    if(error!=dynamic::error::none){std::fprintf(stderr,"generation error=%u\n",static_cast<u32>(error));return 1;}
    std::printf("{\"id\":%llu,\"main\":\"%s\"}\n",static_cast<unsigned long long>(result.header.id),result.objects[2].path);
}
'''


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def guest_path(value):
    if (not value.startswith('/') or len(value.encode()) >= 128 or value.endswith('/')
            or any(part in ('', '.', '..') or not re.fullmatch(r'[A-Za-z0-9_.+-]+', part)
                   for part in value[1:].split('/'))):
        raise ValueError('generation guest path must be canonical and bounded')
    return value


def anchor_sdk(path, manifest_sha, tree_sha):
    if sha(path / 'manifest.json') != manifest_sha:
        raise ValueError('C SDK differs from independently supplied manifest anchor')
    binding = inspect_sdk('glibc', path)['binding']
    if binding['sdk_manifest_sha256'] != manifest_sha or binding['sdk_tree_sha256'] != tree_sha:
        raise ValueError('complete C SDK differs from independently supplied anchors')
    return binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--system-source', type=Path, default=ROOT,
                        help='immutable checkout that produced --system; checked against every system source hash')
    parser.add_argument('--sdk-manifest-sha256', required=True)
    parser.add_argument('--sdk-tree-sha256', required=True)
    parser.add_argument('--generation', action='append', nargs=2, required=True, metavar=('LOCAL_BINARY', 'GUEST_PATH'))
    args = parser.parse_args()
    if not 1 <= len(args.generation) <= 4:
        parser.error('explicitly approve one to four generation records')
    for value in (args.sdk_manifest_sha256, args.sdk_tree_sha256):
        if not re.fullmatch('[0-9a-f]{64}', value):
            parser.error('SDK anchors must be independent literal lowercase SHA-256 values')
    system, system_source, c_sdk = (p.resolve(strict=True) for p in (args.system, args.system_source, args.sdk_build))
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'native controller with compile-time approved roots',
              'guest': 'not_run', 'commands': [], 'approved_generations': []}
    def run(command, name):
        report['commands'].append(list(map(str, command)))
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    try:
        native_manifest = bind_system(system, system_source)
        native_sdk = system / 'sdk'
        native_binding = verify_sdk(native_sdk, native_manifest)
        metadata = json.loads((native_sdk / 'manifest.json').read_bytes())
        if 'archive_provenance' not in metadata:
            raise ValueError('native SDK requires archive-member provenance')
        native_provenance = verify_bundle(native_sdk, metadata['archive_provenance'], ('lib/libc.a', 'lib/libm.a'))
        c_binding = anchor_sdk(c_sdk, args.sdk_manifest_sha256, args.sdk_tree_sha256)
        inputs = [ROOT / path for path in INPUTS]
        headers = [p for directory in ('src/shared/include/xos', 'src/user/include/xos')
                   for p in (ROOT / directory).glob('*') if p.suffix in ('.h', '.hpp')]
        inputs += headers
        source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
        for path in headers:
            # user_build deliberately keeps the private scheduler core out of
            # the native SDK; all exported shared/public headers remain bound.
            if path.name == 'thread_core.hpp':
                continue
            exported = native_sdk / 'include/xos' / path.name
            if not exported.is_file() or sha(exported) != source_hashes[str(path.relative_to(ROOT))]:
                raise ValueError('native SDK header differs: ' + path.name)
        snapshot = out / 'sdk_snapshot'
        snapshot.mkdir()
        shutil.copytree(c_sdk / 'sysroot', snapshot / 'sysroot', symlinks=True)
        shutil.copyfile(c_sdk / 'manifest.json', snapshot / 'manifest.json')
        for directory in ('source_verification', 'gcc_source_verification'):
            if (c_sdk / directory).is_dir():
                shutil.copytree(c_sdk / directory, snapshot / directory, symlinks=True)
        if (c_sdk / 'terminal_support/manifest.json').is_file():
            (snapshot / 'terminal_support').mkdir()
            shutil.copyfile(c_sdk / 'terminal_support/manifest.json', snapshot / 'terminal_support/manifest.json')
        if (anchor_sdk(c_sdk, args.sdk_manifest_sha256, args.sdk_tree_sha256) != c_binding
                or anchor_sdk(snapshot, args.sdk_manifest_sha256, args.sdk_tree_sha256) != c_binding):
            raise ValueError('C SDK changed during complete snapshot copy')
        native_copy = out / 'native_sdk_snapshot'
        shutil.copytree(native_sdk, native_copy, symlinks=True)
        if verify_sdk(native_copy, native_manifest) != native_binding:
            raise ValueError('native SDK snapshot differs')
        validator = out / 'validate_generation.cpp'
        validator.write_text(VALIDATOR)
        run([os.environ.get('CXX', 'g++'), '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror',
             '-I', str(ROOT / 'src/shared/include'), '-I', str(ROOT / 'src/user/include'),
             str(validator), str(ROOT / 'src/user/loader/dynamic/generation.cpp'),
             str(ROOT / 'src/user/loader/dynamic/identity.cpp'), '-o', str(out / 'validate_generation')], 'validator')
        selected, main_paths, original_generations = [], [], {}
        for index, (local, guest) in enumerate(args.generation):
            path = Path(local).resolve(strict=True)
            guest_path(guest)
            original_generations[path] = sha(path)
            frozen = out / ('generation_' + str(index) + '.bin')
            shutil.copyfile(path, frozen)
            if sha(frozen) != original_generations[path]:
                raise ValueError('generation changed during snapshot copy')
            info = json.loads(subprocess.check_output([str(out / 'validate_generation'), str(frozen), args.sdk_manifest_sha256]))
            root = {'id': info['id'], 'sha256': sha(frozen), 'manifest': guest, 'main': info['main'], 'snapshot': frozen.name}
            if any(item['id'] == root['id'] or item['sha256'] == root['sha256'] or item['manifest'] == guest for item in selected):
                raise ValueError('duplicate approved generation identity, digest or manifest path')
            selected.append(root); main_paths.append(info['main'])
        byte_array = lambda value: '{' + ','.join(str(n) for n in bytes.fromhex(value)) + '}'
        roots = ['{{' + str(item['id']) + 'ULL,' + byte_array(item['sha256']) + '},' + json.dumps(item['manifest']) + '}' for item in selected]
        (out / 'dynamic_roots.hpp').write_text('// Generated only from explicitly approved build inputs.\n'
            'inline constexpr xos::dynamic::launch_policy dynamic_run_approved{' + str(len(roots)) + ',0,1,0,0,'
            + byte_array(args.sdk_manifest_sha256) + ',{' + ','.join(roots) + '}};\n'
            'inline constexpr const char* dynamic_run_main_paths[]{' + ','.join(json.dumps(p) for p in main_paths) + '};\n')
        binary = out / 'dynamic-run.elf'
        run([tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow',
             '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '-fno-use-cxa-atexit',
             '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
             '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++', '-I', str(native_copy / 'include'), '-I', str(out),
             str(ROOT / 'src/user/tools/dynamic_run.cpp'), '-nostdlib', '-static', '-no-pie',
             '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
             '-T', str(native_copy / 'user.ld'), str(native_copy / 'crt0.o'), '-Wl,--start-group',
             str(native_copy / 'lib/libxos.a'), str(native_copy / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)], 'launcher')
        run([tool('objcopy'), '--strip-debug', str(binary)], 'strip')
        if binary.stat().st_size > 131072:
            raise ValueError('native controller exceeds the ordinary loader file bound')
        if source_hashes != {str(p.relative_to(ROOT)): sha(p) for p in inputs}:
            raise ValueError('controller build source changed')
        if any(sha(path) != digest for path, digest in original_generations.items()):
            raise ValueError('approved generation changed during build')
        if (bind_system(system, system_source) != native_manifest
                or verify_sdk(native_copy, native_manifest) != native_binding
                or anchor_sdk(c_sdk, args.sdk_manifest_sha256, args.sdk_tree_sha256) != c_binding
                or anchor_sdk(snapshot, args.sdk_manifest_sha256, args.sdk_tree_sha256) != c_binding):
            raise ValueError('bound SDK/system changed during build')
        report.update(status='built_not_run', sources=source_hashes, approved_generations=selected,
                      sdk_manifest_sha256=args.sdk_manifest_sha256, sdk_tree_sha256=args.sdk_tree_sha256,
                      c_sdk_binding=c_binding, native_system_build_id=native_manifest['build_id'],
                      native_system_manifest_sha256=sha(system / 'manifest.json'), native_sdk_binding=native_binding,
                      native_archive_provenance=native_provenance, toolchain=audit(),
                      artifacts={binary.name: sha(binary), 'dynamic_roots.hpp': sha(out / 'dynamic_roots.hpp')})
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
