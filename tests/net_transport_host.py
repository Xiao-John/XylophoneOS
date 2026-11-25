#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile actual C++17 native transport/HTTP with a controlled IPC boundary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    names = ('src/shared/include/xos/net_service_abi.hpp', 'src/user/include/xos/net_service_client.hpp',
             'src/user/include/xos/net_transport.hpp', 'src/ports/browser_http/http.hpp',
             'src/ports/browser_http/http.cpp', 'src/ports/browser_http/transport.hpp',
             'src/ports/browser_http/transport.cpp', 'tests/fixtures/network/client_transport_host.cpp',
             'tests/fixtures/network/transport_host.cpp', 'tests/fixtures/network/net_transport_probe.cpp',
             'tests/net_transport_host.py', 'src/user/sdk/text.cpp', 'src/user/arch/x86_64/syscall.cpp',
             'src/shared/runtime/memory.cpp', 'src/user/arch/x86_64/user.ld')
    names = tuple(sorted(set(names) | {path.relative_to(ROOT).as_posix()
        for folder in ('src/shared/include', 'src/user/include')
        for path in (ROOT / folder).rglob('*.hpp')}))
    def sources():
        return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    before = sources()
    compiler = os.environ.get('CXX', 'c++')
    flags = ['-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wconversion', '-Wshadow',
             '-I', str(ROOT / 'src/shared/include'), '-idirafter', str(ROOT / 'src/user/include'),
             '-I', str(ROOT / 'src/ports/browser_http')]
    base_flags = list(flags)
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                  '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
    environment = os.environ.copy()
    environment.setdefault('ASAN_OPTIONS', 'detect_leaks=0')
    results = []
    with tempfile.TemporaryDirectory(prefix='xos_net_transport_') as temporary:
        for name in ('client_transport_host', 'transport_host'):
            binary = Path(temporary) / name
            inputs = [ROOT / 'tests/fixtures/network' / (name + '.cpp')]
            if name == 'transport_host':
                inputs += [ROOT / 'src/ports/browser_http/transport.cpp', ROOT / 'src/ports/browser_http/http.cpp']
            subprocess.run([compiler, *flags, *map(str, inputs), '-o', str(binary)], check=True)
            completed = subprocess.run([str(binary)], env=environment, capture_output=True, text=True)
            print(completed.stdout, end='')
            if completed.stderr:
                print(completed.stderr, end='')
            completed.check_returncode()
            results.append({'case': name, 'stdout': completed.stdout})
        subprocess.run([compiler, *flags, '-ffreestanding', '-fno-exceptions', '-fno-rtti',
                        '-fsyntax-only', str(ROOT / 'tests/fixtures/network/net_transport_probe.cpp')], check=True)
        # Link all actual native pieces without libc; the tiny entry roots the
        # executable for host linker QA only and is never executed as XOS.
        objects = []
        for name in ('tests/fixtures/network/net_transport_probe.cpp', 'src/ports/browser_http/http.cpp',
                     'src/ports/browser_http/transport.cpp', 'src/user/sdk/text.cpp',
                     'src/user/arch/x86_64/syscall.cpp', 'src/shared/runtime/memory.cpp'):
            obj = Path(temporary) / (Path(name).stem + '.o')
            subprocess.run([compiler, *base_flags, '-Os', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
                            '-fno-stack-protector', '-fno-pie', '-fno-pic', '-mno-red-zone', '-mgeneral-regs-only',
                            '-ffunction-sections', '-fdata-sections', '-fno-unwind-tables',
                            '-fno-asynchronous-unwind-tables', '-c', str(ROOT / name), '-o', str(obj)], check=True)
            objects.append(str(obj))
        entry = Path(temporary) / 'entry.s'
        entry.write_text('.section .text.entry\n.global _start\n_start:\ncall xos_user_main\nud2\n'
                         '.section .note.GNU-stack,"",@progbits\n')
        subprocess.run([compiler, '-c', str(entry), '-o', str(Path(temporary) / 'entry.o')], check=True)
        subprocess.run([compiler, '-nostdlib', '-static', '-no-pie',
                        '-Wl,--gc-sections,--no-undefined,--build-id=none,-z,noexecstack',
                        '-T', str(ROOT / 'src/user/arch/x86_64/user.ld'), str(Path(temporary) / 'entry.o'),
                        *objects, '-o', str(Path(temporary) / 'probe.elf')], check=True)
        results.append({'case': 'host_freestanding_probe_link', 'libc_linked': False})
    if before != sources():
        raise ValueError('source changed during host validation')
    result = {'status': 'passed', 'sanitize': args.sanitize, 'leak_sanitizer': 'not_run_ptrace',
              'sources': before, 'results': results, 'guest': 'not_run',
              'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0]}
    if args.output:
        output = args.output.resolve()
        output.relative_to(ROOT / 'build')
        output.mkdir(parents=True, exist_ok=True)
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS native probe strict freestanding syntax + host link without libc; frozen target/guest NOT_RUN')


if __name__ == '__main__':
    main()
