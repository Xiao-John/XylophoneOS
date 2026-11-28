#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the native IPC exec lifecycle probe with a recorded SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from toolchain import audit, tool
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]
SDK_HEADERS = ('src/shared/include/xos/process_abi.hpp', 'src/user/include/xos/sdk.hpp',
               'src/shared/include/xos/thread_abi.hpp', 'src/user/include/xos/ipc_v1.hpp',
               'src/shared/include/xos/ipc_v1_abi.hpp')
INPUTS = ('tests/fixtures/ipc_exec/ipc_exec_probe.cpp', *SDK_HEADERS,
          'src/user/include/xos/thread_core.hpp', 'src/user/arch/x86_64/thread_core.cpp',
          'scripts/build_ipc_exec_probe.py')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(strict=True), args.output.absolute()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    versions = audit()
    for name in SDK_HEADERS:
        if sha(ROOT / name) != sha(sdk / 'include/xos' / Path(name).name):
            raise ValueError('SDK header differs from current source: ' + name)
    sources = {name: sha(ROOT / name) for name in INPUTS}
    sdk_hash = tree_receipt(sdk)[0]
    # The mechanism-only worker profile is deliberately separate from libc.
    # Compile the recorded native core against this SDK; never enable the
    # single-thread application libc in a multithreaded probe.
    include = out / 'include/xos'
    include.mkdir(parents=True)
    shutil.copyfile(ROOT / 'src/user/include/xos/thread_core.hpp', include / 'thread_core.hpp')
    binary = out / 'ipc_exec_probe.elf'
    command = [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
               '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
               '-fno-use-cxa-atexit', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
               '-fno-stack-protector', '-fno-pic', '-fno-pie', '-mno-red-zone', '-mgeneral-regs-only',
               '-nostdinc++', '-ffunction-sections', '-fdata-sections', '-I', str(include.parent),
               '-idirafter', str(sdk / 'include'), str(ROOT / INPUTS[0]),
               str(ROOT / 'src/user/arch/x86_64/thread_core.cpp'), '-nostdlib', '-static', '-no-pie',
               '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
               '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), '-Wl,--start-group',
               str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)]
    subprocess.run(command, check=True)
    subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], check=True)
    if binary.stat().st_size > 131072:
        raise ValueError('fixture exceeds loader image bound')
    if sources != {name: sha(ROOT / name) for name in INPUTS} or sdk_hash != tree_receipt(sdk)[0]:
        raise ValueError('build inputs changed during compilation')
    receipt = {'sources': sources, 'sdk_tree_sha256': sdk_hash,
               'artifacts': {binary.name: sha(binary)}, 'toolchain': versions,
               'commands': [command], 'libc_linked': False}
    (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
