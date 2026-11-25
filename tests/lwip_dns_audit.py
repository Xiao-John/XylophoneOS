#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Audit disabled lwIP DNS using real parser/stack and a local Ethernet fixture.

Results distinguish successful audit execution from failed activation gates.
No production configuration, external network, or guest qualification is implied.
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
from lwip_service_build import core_sources, ipv4_sources, extract_source


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / 'build')
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'not_run', 'production_dns_enabled': False, 'guest': 'not_run',
              'scope': 'Locked upstream DNS, actual XOS lwip_stack and Ethernet/IP/UDP; local simulated peer and entropy source.',
              'commands': [], 'observations': []}
    own = [Path(__file__).resolve(), ROOT / 'tests/fixtures/network/dns_upstream_audit.cpp',
           ROOT / 'src/user/network/lwip_stack.cpp', ROOT / 'src/user/network/lwip_stack.hpp',
           ROOT / 'src/user/network/service_core.hpp', ROOT / 'src/shared/include/xos/net_service_abi.hpp',
           ROOT / 'src/shared/include/xos/abi_types.hpp',
           ROOT / 'src/user/network/include/lwipopts.h', ROOT / 'src/ports/lwip/include/lwipopts.h',
           ROOT / 'src/user/network/include/arch/cc.h', ROOT / 'src/ports/lwip/include/arch/cc.h',
           ROOT / 'scripts/lwip_service_build.py', ROOT / 'src/ports/lwip/source_lock.json']
    report['inputs'] = {str(path.relative_to(ROOT)): sha(path) for path in sorted(own)}
    ignored = ('CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
               'LIBRARY_PATH', 'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LD_PRELOAD')
    environment = {key: value for key, value in os.environ.items() if key not in ignored}
    report['sanitized_environment'] = [key for key in ignored if key in os.environ]
    report['tools'] = {}
    for variable, default in [('CC', 'cc'), ('CXX', 'c++')]:
        path = shutil.which(os.environ.get(variable, default))
        if path is None:
            raise RuntimeError(f'compiler unavailable: {variable}')
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
        source = extract_source(args.archive, output / 'source', lock['sha256'])
        report['archive_sha256'] = lock['sha256']
        include = output / 'include'; include.mkdir()
        options = include / 'lwipopts.h'
        options.write_text('#include "' + str(ROOT / 'src/user/network/include/lwipopts.h')
                           + '"\n#undef LWIP_DNS\n#define LWIP_DNS 1\n')
        report['test_only_options'] = ['Production options unchanged; test include overrides LWIP_DNS=1.']
        flags = ['-O2', '-g', '-I', str(include), '-I', str(ROOT / 'src/user/network/include'),
                 '-I', str(ROOT / 'src/ports/lwip/include'), '-I', str(source / 'src/include'),
                 '-I', str(ROOT / 'src/shared/include'), '-I', str(ROOT / 'src/user')]
        sources = [source / 'src/core' / name for name in [*core_sources, 'dns.c']]
        sources += [source / 'src/core/ipv4' / name for name in ipv4_sources]
        sources += [source / 'src/netif/ethernet.c']
        report['upstream_inputs'] = {str(path.relative_to(source)): sha(path) for path in sources}
        objects = []
        for path in sources:
            target = output / (path.relative_to(source).as_posix().replace('/', '_') + '.o')
            run([report['tools']['CC']['path'], '-std=c11', *flags, '-c', str(path), '-o', str(target)])
            objects.append(str(target))
        binary = output / 'dns_upstream_audit'
        run([report['tools']['CXX']['path'], '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags,
             str(ROOT / 'tests/fixtures/network/dns_upstream_audit.cpp'),
             str(ROOT / 'src/user/network/lwip_stack.cpp'), *objects, '-o', str(binary)])
        cases = {'valid': (0, 'accepted=1', 'control_pass'),
                 'wrong_id': (0, 'accepted=0', 'control_pass'),
                 'wrong_question': (0, 'accepted=0', 'control_pass'),
                 'wrong_source_address': (0, 'accepted=0', 'control_pass'),
                 'wrong_source_port': (0, 'accepted=1', 'activation_gate_failed'),
                 'other_query_port': (0, 'accepted=1', 'activation_gate_failed'),
                 'unrelated_owner': (0, 'accepted=1', 'activation_gate_failed'),
                 'truncated': (0, 'accepted=1', 'activation_gate_failed'),
                 'other_opcode': (0, 'accepted=1', 'activation_gate_failed'),
                 'ttl_pause': (0, 'cached=1', 'activation_gate_failed'),
                 'server_change': (0, 'cached_previous_server=1', 'activation_gate_failed'),
                 'entropy_failure': (42, 'repeated_draws=4096 operation_returned=0', 'activation_gate_failed')}
        for name, (code, marker, status) in cases.items():
            stdout = run([str(binary), name], expected=code)
            if marker not in stdout:
                raise RuntimeError(f'audit observation changed: {name}: {stdout!r}')
            report['observations'].append({'case': name, 'status': status, 'output': stdout.strip()})
        for relative, digest in report['inputs'].items():
            if sha(ROOT / relative) != digest:
                raise RuntimeError(f'audit input changed: {relative}')
        for tool in report['tools'].values():
            if sha(Path(tool['path'])) != tool['sha256']:
                raise RuntimeError('audit compiler changed during execution')
        report['binary_sha256'] = sha(binary)
        report['status'] = 'audit_complete_activation_blocked'
    except BaseException as error:
        report['status'] = 'audit_failed'
        report['error'] = str(error)
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('AUDIT_COMPLETE: 4 controls observed; 8 DNS activation gates failed; production remains disabled')


if __name__ == '__main__':
    main()
