#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile actual production DHCP/ACD and qualify absolute lease authorization."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from lwip_service_build import core_sources, ipv4_sources, prepare_source, source_input_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', default=os.environ.get('XOS_LWIP_SOURCE_ARCHIVE'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    if not args.archive:
        parser.error('verified lwIP archive required')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    source = prepare_source(ROOT, args.archive, out / 'source')
    own = [ROOT / 'src/user/network' / name for name in ('lwip_stack.cpp', 'lwip_dhcp.cpp', 'dhcp_policy.cpp', 'service_core.cpp')]
    fixture = ROOT / 'tests/fixtures/network/dhcp_stack_host.cpp'
    inputs = [Path(__file__), fixture, *own, *source_input_paths(ROOT), ROOT / 'scripts/lwip_service_build.py',
              ROOT / 'src/shared/include/xos/net_service_abi.hpp', *sorted((ROOT / 'src/user/network').glob('*.hpp')),
              ROOT / 'src/user/network/include/lwipopts.h', ROOT / 'src/ports/lwip/include/lwipopts.h']
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
    includes = [value for path in ('src/user/network/include', 'src/ports/lwip/include', 'src/shared/include', 'src/user') for value in ('-I', str(ROOT / path))]
    includes += ['-I', str(source / 'src/include')]
    sanitizer = ['-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-fno-omit-frame-pointer'] if args.sanitize else []
    flags = ['-O1', '-g', '-DXOS_NET_DHCP_PROFILE=1', *sanitizer, *includes]
    cc, cxx = os.environ.get('CC', 'cc'), os.environ.get('CXX', 'c++')
    upstream = [source / 'src/core' / name for name in [*core_sources, 'dns.c']]
    upstream += [source / 'src/core/ipv4' / name for name in [*ipv4_sources, 'dhcp.c', 'acd.c']]
    upstream += [source / 'src/netif/ethernet.c']
    objects = []
    for path in upstream:
        target = out / (path.stem + '.o')
        subprocess.run([cc, '-std=c11', *flags, '-c', str(path), '-o', str(target)], check=True, timeout=90)
        objects.append(str(target))
    binary = out / 'dhcp_stack_host'
    subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, str(fixture), *map(str, own), *objects, '-o', str(binary)], check=True, timeout=90)
    cases = subprocess.check_output([str(binary), '--list'], text=True).splitlines()
    for case in cases:
        subprocess.run([str(binary), case], check=True, timeout=30)
    for name, digest in hashes.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('source changed while qualifying: ' + name)
    receipt = {'guest_qualification': 'not_run', 'scenarios': cases, 'sanitizers': ['address', 'undefined'] if args.sanitize else [], 'inputs': hashes, 'asan_options': os.environ.get('ASAN_OPTIONS', '')}
    (out / 'result.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print('DHCP_PRODUCTION_SCENARIOS_PASSED=' + str(len(cases)))

if __name__ == '__main__':
    main()
