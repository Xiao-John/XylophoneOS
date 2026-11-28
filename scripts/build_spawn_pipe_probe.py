#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Link real glibc spawn/FD code with the selected production loader object."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from build_dynamic_program import inspect_native_sdk
from glibc_g1_probe import clean_build_environment, tool_identity
from sdk_receipt import sha, verify_sdk
from shell_launch_support import bind_system
from xypm_sdk_profile import inspect_sdk

INPUTS = ('scripts/build_spawn_pipe_probe.py', 'tests/fixtures/glibc_g3/spawn_pipe_routes.c',
          'src/user/loader/load.cpp', 'src/user/loader/image_reader.hpp',
          'scripts/build_dynamic_program.py', 'scripts/glibc_g1_probe.py',
          'scripts/xypm_sdk_profile.py', 'scripts/sdk_receipt.py', 'tests/shell_launch_support.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'sdk-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('sdk-manifest-sha256', 'sdk-tree-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    system, source, sdk = (path.resolve(strict=True) for path in
                           (args.system, args.system_source, args.sdk_build))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'guest': 'not_run', 'commands': [],
              'sources': {name: sha(ROOT / name) for name in INPUTS}}
    try:
        system_manifest = bind_system(system, source)
        native = inspect_native_sdk(system / 'sdk')
        verify_sdk(system / 'sdk', system_manifest)
        binding = inspect_sdk('glibc', sdk)['binding']
        if (binding['sdk_manifest_sha256'] != args.sdk_manifest_sha256 or
                binding['sdk_tree_sha256'] != args.sdk_tree_sha256):
            raise ValueError('independent C SDK anchors differ')
        sysroot = out / 'sysroot'
        shutil.copytree(sdk / 'sysroot', sysroot, symlinks=False)
        (out / 'include').mkdir()
        shutil.copytree(system / 'sdk/include/xos', out / 'include/xos')
        snapshot_hashes = {str(p.relative_to(out)): sha(p) for directory in (sysroot, out / 'include')
                           for p in sorted(directory.rglob('*')) if p.is_file()}
        original_hashes = {'sysroot/' + str(p.relative_to(sdk / 'sysroot')): sha(p)
                           for p in sorted((sdk / 'sysroot').rglob('*')) if p.is_file()}
        original_hashes.update({'include/xos/' + str(p.relative_to(system / 'sdk/include/xos')): sha(p)
                               for p in sorted((system / 'sdk/include/xos').rglob('*')) if p.is_file()})
        if snapshot_hashes != original_hashes:
            raise ValueError('full SDK/header snapshot differs')
        import os
        environment, removed = clean_build_environment(os.environ)
        environment['LC_ALL'] = 'C'
        tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'objcopy')}
        seed = json.loads((sdk / 'manifest.json').read_bytes())
        for name, value in tools.items():
            if value['sha256'] != seed['tools']['x86_64-elf-' + name]['sha256']:
                raise ValueError('compiler/binutils differ from anchored SDK')
        report.update(system_build_id=system_manifest['build_id'],
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      sdk_binding=binding, native_sdk_binding=native,
                      snapshot_hashes=snapshot_hashes, tools=tools, sanitized_environment=removed)

        def run(label, command):
            command = list(map(str, command))
            report['commands'].append({'name': label, 'command': command})
            with (out / (label + '.log')).open('w') as log:
                result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            report['commands'][-1].update(exit_code=result.returncode, log_sha256=sha(out / (label + '.log')))
            if result.returncode:
                raise RuntimeError(label + ' failed')

        common = ['--sysroot=' + str(sysroot), '-O2', '-g', '-mno-red-zone', '-fno-pie',
                  '-fno-omit-frame-pointer', '-ftls-model=local-exec', '-nostdinc', '-Wall', '-Wextra',
                  '-Werror', '-Wconversion', '-Wshadow', '-isystem', sysroot / 'usr/include',
                  '-isystem', sysroot / 'usr/lib/compiler-include']
        run('compile-fixture', [tools['gcc']['path'], *common, '-std=gnu11', '-fno-builtin', '-c',
                               ROOT / INPUTS[1], '-o', out / 'probe.o'])
        run('compile-loader', [tools['g++']['path'], *common, '-std=gnu++20', '-nostdinc++',
                              '-ffreestanding', '-fno-builtin', '-fno-exceptions', '-fno-rtti',
                              '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-stack-protector',
                              '-ffunction-sections', '-fdata-sections', '-fvisibility=hidden',
                              '-I', out / 'include', '-MMD', '-MF', out / 'load.d',
                              '-c', ROOT / 'src/user/loader/load.cpp', '-o', out / 'load.o'])
        lib = sysroot / 'usr/lib'
        unwind = [lib / 'libgcc_eh.a'] if (lib / 'libgcc_eh.a').is_file() else []
        run('link', [tools['gcc']['path'], '--sysroot=' + str(sysroot), '-static', '-no-pie', '-nostdlib',
                     '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T', sysroot / 'user.ld',
                     '-o', out / 'spawn_pipe.elf', lib / 'xos_start.o', lib / 'crti.o', lib / 'crtbegin.o',
                     lib / 'xos_start_c.o', lib / 'xos_stdio_receiver.o', out / 'probe.o', out / 'load.o',
                     '-Wl,--start-group', lib / 'libc.a', lib / 'libm.a', lib / 'libxos_terminal.a',
                     lib / 'libgcc.a', *unwind, '-Wl,--end-group', lib / 'crtend.o', lib / 'crtn.o'])
        run('strip', [tools['objcopy']['path'], '--strip-debug', out / 'spawn_pipe.elf'])
        if (inspect_sdk('glibc', sdk)['binding'] != binding or
                bind_system(system, source) != system_manifest or
                inspect_native_sdk(system / 'sdk') != native or
                any(sha(out / name) != expected for name, expected in snapshot_hashes.items()) or
                report['sources'] != {name: sha(ROOT / name) for name in INPUTS}):
            raise ValueError('source or SDK changed during compilation')
        report.update(status='built_not_run', scope='finite real loader object override; no libc or kernel model',
                      system_build_id=system_manifest['build_id'],
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      sdk_binding=binding, native_sdk_binding=native,
                      snapshot_hashes=snapshot_hashes, tools=tools, sanitized_environment=removed,
                      artifacts={name: sha(out / name) for name in ('spawn_pipe.elf', 'load.o', 'probe.o')})
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
