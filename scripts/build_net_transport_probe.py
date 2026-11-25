#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the native N3 guest probe using a matching frozen SDK, without libc."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from toolchain import audit, tool
from xos_app import tree_receipt

INPUTS = ('tests/fixtures/network/net_transport_probe.cpp',
          'src/ports/browser_http/http.hpp', 'src/ports/browser_http/http.cpp',
          'src/ports/browser_http/transport.hpp', 'src/ports/browser_http/transport.cpp',
          'src/user/include/xos/net_transport.hpp', 'src/user/include/xos/net_service_client.hpp',
          'src/shared/include/xos/net_service_abi.hpp', 'scripts/build_net_transport_probe.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=True)
    versions = audit()
    for source, installed in (('src/user/include/xos/net_transport.hpp', 'net_transport.hpp'),
                              ('src/user/include/xos/net_service_client.hpp', 'net_service_client.hpp'),
                              ('src/shared/include/xos/net_service_abi.hpp', 'net_service_abi.hpp')):
        if sha(ROOT / source) != sha(sdk / 'include/xos' / installed):
            raise ValueError('rebuild SDK: native network headers differ from current sources')
    binary = out / 'net_transport_probe.elf'
    command = [tool('g++'), '-std=c++17', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
               '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
               '-fno-use-cxa-atexit', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
               '-fno-stack-protector', '-fno-pic', '-fno-pie', '-mno-red-zone', '-mgeneral-regs-only',
               '-nostdinc++', '-ffunction-sections', '-fdata-sections',
               '-idirafter', str(sdk / 'include'), '-I', str(ROOT / 'src/ports/browser_http'),
               str(ROOT / INPUTS[0]), str(ROOT / INPUTS[2]), str(ROOT / INPUTS[4]),
               '-nostdlib', '-static', '-no-pie', '-Wl,--gc-sections,--build-id=none,--no-undefined',
               '-Wl,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096', '-T', str(sdk / 'user.ld'),
               str(sdk / 'crt0.o'), str(sdk / 'lib/libxos.a'), '-o', str(binary)]
    sources = {name: sha(ROOT / name) for name in INPUTS}
    sdk_hash = tree_receipt(sdk)[0]
    subprocess.run(command, check=True)
    subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], check=True)
    if binary.stat().st_size > 131072:
        raise ValueError('probe exceeds loader image bound')
    if sources != {name: sha(ROOT / name) for name in INPUTS} or sdk_hash != tree_receipt(sdk)[0]:
        raise ValueError('build inputs changed during compilation')
    receipt = {'sources': sources, 'sdk_tree_sha256': sdk_hash, 'binary_sha256': sha(binary),
               'toolchain': versions, 'command': command, 'libc_linked': False}
    (out / 'net_transport_probe.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(binary)


if __name__ == '__main__':
    main()
