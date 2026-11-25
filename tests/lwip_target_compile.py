#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile the current native network sources with an explicit release SDK.

This is a target compile gate, with a separate test-only DNS translation unit.
It does not link an application, build an SDK/ISO, or execute a guest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lwip_service_build import build, source_input_paths


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=os.environ.get('XOS_SDK'), required='XOS_SDK' not in os.environ)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, output = args.sdk.resolve(), args.output.resolve()
    output.relative_to(ROOT / 'build')
    output.mkdir(parents=True, exist_ok=False)
    os.environ['XOS_LWIP_SOURCE_ARCHIVE'] = str(args.archive.resolve())
    report = {'status': 'not_run', 'scope': 'x86_64-elf compile only', 'guest': 'not_run',
              'sdk_rebuilt': False, 'iso_built': False, 'commands': [], 'tools': {}, 'inputs': {},
              'sdk_manifest_sha256': sha(sdk / 'manifest.json'),
              'sdk_build_id': json.loads((sdk / 'manifest.json').read_text()).get('build_id')}
    dependency_files = []
    tools = {}
    for suffix in ('gcc', 'g++'):
        path = shutil.which('x86_64-elf-' + suffix)
        if not path:
            raise RuntimeError('release cross compiler missing: ' + suffix)
        tools[suffix] = path
        report['tools'][suffix] = {'path': path, 'sha256': sha(Path(path)),
                                  'version': subprocess.check_output([path, '--version'], text=True).splitlines()[0]}
    patch = shutil.which('patch')
    if not patch:
        raise RuntimeError('patch tool missing')
    report['tools']['patch'] = {'path': patch, 'sha256': sha(Path(patch)),
                              'version': subprocess.check_output([patch, '--version'], text=True).splitlines()[0]}
    initial = [Path(__file__).resolve(), ROOT / 'scripts/lwip_service_build.py', *source_input_paths(ROOT)]
    report['inputs'] = {str(path): sha(path) for path in initial}

    def run(command):
        command = list(map(str, command))
        if '-c' in command:
            dep = Path(command[command.index('-o') + 1]).with_suffix('.d')
            dependency_files.append(dep)
            command += ['-MD', '-MF', str(dep)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        report['commands'].append({'argv': command, 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise RuntimeError(result.stderr)

    try:
        isa = ['-m64', '-mno-red-zone', '-mgeneral-regs-only']
        objects, includes, config = build(ROOT, output, sdk, run, tools.__getitem__, isa)
        report['production_configuration'] = config
        common = ['-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', '-ffreestanding',
                  '-fno-exceptions', '-fno-rtti', '-fno-stack-protector', '-fno-pie', '-fno-pic',
                  '-nostdinc++', *isa, '-I', str(ROOT / 'src/shared/include'),
                  '-I', str(ROOT / 'src/user/include'), '-I', str(sdk / 'include'), *includes]
        for name, path, extra in [
            ('core', 'src/user/network/service_core.cpp', []),
            ('stack', 'src/user/network/lwip_stack.cpp', []),
            ('loop', 'src/user/network/service_loop.cpp', []),
            ('raw_entry', 'src/user/programs/net_service.cpp', []),
            ('native_entry', 'src/user/programs/net_service.cpp', ['-DXOS_NET_STACK=1'])]:
            target = output / (name + '.o')
            run([tools['g++'], *common, *extra, '-c', ROOT / path, '-o', target])
            objects.append(str(target))
        # Exercise the enabled DNS C code only in an isolated compile profile.
        include = output / 'dns_test_include'; include.mkdir()
        (include / 'lwipopts.h').write_text('#include "' + str(ROOT / 'src/user/network/include/lwipopts.h')
                                          + '"\n#undef LWIP_DNS\n#define LWIP_DNS 1\n')
        source = output / 'net_lwip/source/lwip-2.2.1/src/core/dns.c'
        target = output / 'dns_test_only.o'
        run([tools['gcc'], '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffreestanding', *isa,
             '-I', include, '-I', sdk / 'include', *includes, '-c', source, '-o', target])
        objects.append(str(target))
        for dep in dependency_files:
            text = dep.read_text().replace('\\\n', ' ')
            for name in shlex.split(text.split(':', 1)[1]):
                path = Path(name).resolve()
                report['inputs'][str(path)] = sha(path)
        for name, digest in report['inputs'].items():
            if sha(Path(name)) != digest:
                raise RuntimeError('compile input changed: ' + name)
        for tool in report['tools'].values():
            if sha(Path(tool['path'])) != tool['sha256']:
                raise RuntimeError('build tool changed during compile')
        report['objects'] = {str(Path(path).relative_to(output)): sha(Path(path)) for path in objects}
        report['status'] = 'target_compile_pass_guest_not_run'
    except BaseException as error:
        report['status'] = 'failed'; report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('NETWORK_PREVIEW_TARGET_COMPILE_PASS objects=' + str(len(objects)))


if __name__ == '__main__':
    main()
