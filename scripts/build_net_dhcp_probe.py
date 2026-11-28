#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the native DHCP lifecycle fixture against one verified SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from toolchain import audit, tool
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('tests/fixtures/network/net_dhcp_probe.cpp',
          'tests/fixtures/network/net_dhcp_probe.cpp',
          'src/user/include/xos/net_service_client.hpp',
          'src/shared/include/xos/net_service_abi.hpp',
          'scripts/build_net_dhcp_probe.py')
RESOLVER_FIXTURE = 'tests/fixtures/network/net_resolver_probe.cpp'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    versions = audit()
    for source in INPUTS[2:4]:
        if sha(ROOT / source) != sha(sdk / 'include/xos' / Path(source).name):
            raise ValueError('SDK network headers differ from current sources')
    inputs = (INPUTS[0], *INPUTS[2:])
    sources = {name: sha(ROOT / name) for name in inputs}
    sdk_hash = tree_receipt(sdk)[0]
    artifacts, commands = {}, []
    programs = ((INPUTS[0], 'net_dhcp_probe.elf'),)
    for source, name in programs:
        binary = out / name
        command = [tool('g++'), '-std=c++17', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
                   '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
                   '-fno-use-cxa-atexit', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                   '-fno-stack-protector', '-fno-pic', '-fno-pie', '-mno-red-zone', '-mgeneral-regs-only',
                   '-nostdinc++', '-ffunction-sections', '-fdata-sections', '-idirafter', str(sdk / 'include'),
                   str(ROOT / source), '-nostdlib', '-static', '-no-pie',
                   '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                   '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), '-Wl,--start-group',
                   str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)]
        subprocess.run(command, check=True)
        subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], check=True)
        if binary.stat().st_size > 131072:
            raise ValueError('fixture exceeds loader image bound')
        artifacts[name] = sha(binary)
        commands.append(command)
    if sources != {name: sha(ROOT / name) for name in inputs} or sdk_hash != tree_receipt(sdk)[0]:
        raise ValueError('build inputs changed during compilation')
    receipt = {'sources': sources, 'sdk_tree_sha256': sdk_hash, 'artifacts': artifacts,
               'toolchain': versions, 'commands': commands, 'libc_linked': False}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
