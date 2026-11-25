#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify N4-D1 patches using the actual parser/stack and local Ethernet frames.

Production DNS/DHCP stay disabled. D2 lifecycle and D3 guest gates are pending.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lwip_service_build import core_sources, ipv4_sources, prepare_source, source_input_paths


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / 'build')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'not_run', 'production_dns_enabled': False, 'production_dhcp_enabled': False, 'guest': 'not_run',
              'sanitizers': ['address', 'undefined'] if args.sanitize else [],
              'remaining_gates': ['D2 absolute TTL, config invalidation, cancellation, error classes',
                                  'D3 real guest DNS and full DHCP'],
              'scope': 'Hash-bound lwIP patches, actual XOS lwip_stack and Ethernet/IP/UDP; local simulated peer and entropy source.',
              'commands': [], 'observations': []}
    own = [Path(__file__).resolve(), ROOT / 'tests/fixtures/network/dns_hardening_host.cpp',
           ROOT / 'src/user/network/lwip_stack.cpp', ROOT / 'src/user/network/lwip_stack.hpp',
           ROOT / 'src/user/network/service_core.hpp', ROOT / 'src/shared/include/xos/net_service_abi.hpp',
           ROOT / 'src/shared/include/xos/abi_types.hpp',
           ROOT / 'src/user/network/include/lwipopts.h', ROOT / 'src/ports/lwip/include/lwipopts.h',
           ROOT / 'src/user/network/include/arch/cc.h', ROOT / 'src/ports/lwip/include/arch/cc.h',
           ROOT / 'scripts/lwip_service_build.py', *source_input_paths(ROOT)]
    report['inputs'] = {str(path.relative_to(ROOT)): sha(path) for path in sorted(own)}
    ignored = ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
               'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LD_PRELOAD')
    environment = {key: value for key, value in os.environ.items() if key not in ignored}
    report['sanitized_environment'] = [key for key in ignored if key in os.environ]
    if args.sanitize:
        environment['ASAN_OPTIONS'] = 'detect_leaks=0:abort_on_error=1'
        environment['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    report['asan_options'] = environment.get('ASAN_OPTIONS', '')
    report['ubsan_options'] = environment.get('UBSAN_OPTIONS', '')
    report['tools'] = {}
    for variable, default in [('CC', 'cc'), ('CXX', 'c++'), ('PATCH', 'patch')]:
        path = shutil.which(os.environ.get(variable, default))
        if path is None:
            raise RuntimeError(f'build tool unavailable: {variable}')
        executable = Path(path).resolve()
        version = subprocess.check_output([str(executable), '--version'], text=True,
                                          env=environment).splitlines()[0]
        report['tools'][variable] = {'path': str(executable), 'sha256': sha(executable), 'version': version}

    def run(command, expected=0):
        result = subprocess.run(command, text=True, capture_output=True, timeout=90, env=environment)
        report['commands'].append({'argv': command, 'returncode': result.returncode,
                                   'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode != expected:
            raise RuntimeError(f'command failed: {command[0]} returned {result.returncode}, expected {expected}; {result.stderr}')
        return result.stdout

    try:
        lock = json.loads((ROOT / 'src/ports/lwip/source_lock.json').read_text())
        source = prepare_source(ROOT, args.archive, output / 'source',
                                patch_tool=report['tools']['PATCH']['path'], environment=environment)
        report['patches'] = lock.get('patches', [])
        report['archive_sha256'] = lock['sha256']
        include = output / 'include'; include.mkdir()
        options = include / 'lwipopts.h'
        options.write_text('#include "' + str(ROOT / 'src/user/network/include/lwipopts.h')
                           + '"\n#undef LWIP_DNS\n#define LWIP_DNS 1\n')
        report['test_only_options'] = ['Production options unchanged; test include overrides LWIP_DNS=1.']
        sanitizer = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                     '-fno-omit-frame-pointer'] if args.sanitize else []
        linker_flags = []
        if args.sanitize and sys.platform == 'linux':
            sanitizer.append('-fno-pie')
            linker_flags.append('-no-pie')
        flags = ['-O1' if args.sanitize else '-O2', '-g', *sanitizer, '-I', str(include), '-I', str(ROOT / 'src/user/network/include'),
                 '-I', str(ROOT / 'src/ports/lwip/include'), '-I', str(source / 'src/include'),
                 '-I', str(ROOT / 'src/shared/include'), '-I', str(ROOT / 'src/user')]
        sources = [source / 'src/core' / name for name in [*core_sources, 'dns.c']]
        sources += [source / 'src/core/ipv4' / name for name in ipv4_sources]
        sources += [source / 'src/netif/ethernet.c']
        upstream = [*sources, *(path for path in (source / 'src/include').rglob('*') if path.is_file())]
        report['upstream_inputs'] = {str(path.relative_to(source)): sha(path) for path in sorted(upstream)}
        objects = []
        for path in sources:
            target = output / (path.relative_to(source).as_posix().replace('/', '_') + '.o')
            run([report['tools']['CC']['path'], '-std=c11', *flags, '-c', str(path), '-o', str(target)])
            objects.append(str(target))
        binary = output / 'dns_hardening_host'
        run([report['tools']['CXX']['path'], '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, *linker_flags,
             str(ROOT / 'tests/fixtures/network/dns_hardening_host.cpp'),
             str(ROOT / 'src/user/network/lwip_stack.cpp'), *objects, '-o', str(binary)])
        cases = run([str(binary), '--list']).splitlines()
        if len(cases) != len(set(cases)) or len(cases) != 43:
            raise RuntimeError('fixture scenario inventory changed')
        for name in cases:
            stdout = run([str(binary), name])
            if stdout.strip() != 'DNS_HARDENING_CASE_PASS=' + name:
                raise RuntimeError(f'hardening result missing: {name}: {stdout!r}')
            report['observations'].append({'case': name, 'status': 'pass', 'output': stdout.strip()})
        for relative, digest in report['inputs'].items():
            if sha(ROOT / relative) != digest:
                raise RuntimeError(f'audit input changed: {relative}')
        for tool in report['tools'].values():
            if sha(Path(tool['path'])) != tool['sha256']:
                raise RuntimeError('audit compiler changed during execution')
        report['binary_sha256'] = sha(binary)
        report['status'] = 'd1_host_pass_production_disabled'
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'DNS_HARDENING_HOST_CASES_PASSED={len(cases)} sanitizers={args.sanitize}; D2/D3 pending')


if __name__ == '__main__':
    main()
