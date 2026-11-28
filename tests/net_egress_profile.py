#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate trusted profile admission and compile the exact generated authority."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lwip_service_build import load_static_profile, write_egress_header


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = {'revision': 2, 'pci_instance': 41, 'resolver': '10.0.2.2', 'egress': [
        {'cidr': '192.0.2.0/24', 'protocol': 'udp', 'ports': [41001, 41001]}]}
    cases = [('valid_v2', json.dumps(base), True),
             ('valid_v1', json.dumps({'revision': 1, 'pci_instance': 41, 'resolver': '10.0.2.2'}), True)]

    def change(name, path, value, valid=False):
        item = copy.deepcopy(base)
        parent = item
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
        cases.append((name, json.dumps(item), valid))

    change('deny_all', ['egress'], [], True)
    change('explicit_all_addresses', ['egress', 0, 'cidr'], '0.0.0.0/0', True)
    change('host_bits', ['egress', 0, 'cidr'], '192.0.2.1/24')
    change('prefix_out_of_range', ['egress', 0, 'cidr'], '192.0.2.0/33')
    change('missing_prefix', ['egress', 0, 'cidr'], '192.0.2.1')
    change('noncanonical_prefix', ['egress', 0, 'cidr'], '192.0.2.0/255.255.255.0')
    change('ipv6', ['egress', 0, 'cidr'], '2001:db8::/32')
    change('cidr_type', ['egress', 0, 'cidr'], 24)
    change('protocol', ['egress', 0, 'protocol'], 'icmp')
    change('protocol_type', ['egress', 0, 'protocol'], True)
    for name, ports in [('port_zero', [0, 80]), ('port_overflow', [80, 65536]),
                        ('port_reverse', [81, 80]), ('port_bool', [True, 80]),
                        ('port_float', [80.0, 80]), ('port_missing', [80])]:
        change(name, ['egress', 0, 'ports'], ports)
    change('rule_quota', ['egress'], [base['egress'][0]] * 9)
    change('duplicate_rule', ['egress'], base['egress'] * 2)
    change('egress_type', ['egress'], None)
    change('unknown_field', ['egress', 0, 'wildcard'], True)
    change('revision_bool', ['revision'], True)
    change('revision_unknown', ['revision'], 3)
    change('v1_cannot_expand_policy', ['revision'], 1)
    cases.append(('duplicate_json_key', json.dumps(base).replace('"revision": 2', '"revision": 1, "revision": 2'), False))
    cases.append(('oversized', ' ' * 4097, False))
    results = []
    with tempfile.TemporaryDirectory(prefix='xos_egress_profile_') as temporary:
        directory = Path(temporary)
        path = directory / 'profile.json'
        for name, text, valid in cases:
            path.write_text(text)
            try:
                value = load_static_profile(path)
            except (ValueError, TypeError):
                if valid:
                    raise
            else:
                if not valid:
                    raise AssertionError('invalid profile accepted: ' + name)
                if value['source_sha256'] != hashlib.sha256(text.encode()).hexdigest():
                    raise AssertionError('profile source identity differs')
            results.append(name)
        write_egress_header(base['egress'], directory)
        source = directory / 'check.cpp'
        source.write_text('#include "egress_policy.hpp"\n#include "xos_net_egress_profile.hpp"\n'
                          'using namespace xos::user::network;\n'
                          'static_assert(installed_egress_policy.count == 1);\n'
                          'static_assert(egress_permitted(installed_egress_policy, 0xc0000207, xos::net2::protocol::udp, 41001));\n'
                          'static_assert(!egress_permitted(installed_egress_policy, 0xc0000207, xos::net2::protocol::tcp, 41001));\n'
                          'static_assert(!egress_permitted(installed_egress_policy, 0xc0000207, xos::net2::protocol::udp, 41002));\n')
        subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-I', ROOT / 'src/shared/include', '-I', ROOT / 'src/user/network',
                        '-fsyntax-only', source], check=True)
    inputs = [Path(__file__), ROOT / 'scripts/lwip_service_build.py',
              ROOT / 'src/user/network/egress_policy.hpp', ROOT / 'src/shared/include/xos/net_service_abi.hpp']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'status': 'passed', 'cases': results, 'generated_header': 'compiled',
        'guest': 'not_run', 'inputs': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                    for path in inputs}}, indent=2) + '\n')
    print(f'PASS {len(results)} trusted egress profile cases and generated C++ policy')


if __name__ == '__main__':
    main()
