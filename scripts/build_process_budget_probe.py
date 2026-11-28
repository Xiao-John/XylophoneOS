#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build P1-B budget and uncertainty native clients from the matching exported SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from toolchain import audit, tool
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]
HEADERS = (
    'src/shared/include/xos/process_budget_abi.hpp', 'src/shared/include/xos/process_abi.hpp',
    'src/shared/include/xos/thread_abi.hpp', 'src/shared/include/xos/ipc_v1_abi.hpp',
    'src/shared/include/xos/vm_abi.hpp', 'src/user/include/xos/sdk.hpp',
    'src/user/include/xos/dynamic_launch.hpp', 'src/user/include/xos/ipc_v1.hpp',
)
INPUTS = ('tests/fixtures/process_budget_probe.cpp', 'scripts/build_process_budget_probe.py', *HEADERS)



def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(strict=True), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    sources = {name: sha(ROOT / name) for name in INPUTS}
    for name in HEADERS:
        if sha(sdk / 'include/xos' / Path(name).name) != sources[name]:
            raise ValueError('SDK header differs: ' + name)
    sdk_hash = tree_receipt(sdk)[0]
    binary = out / 'budget.elf'
    command = [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
               '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
               '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-unwind-tables',
               '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
               '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++', '-I', str(sdk / 'include'),
               str(ROOT / INPUTS[0]), '-nostdlib', '-static', '-no-pie',
               '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
               '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), '-Wl,--start-group',
               str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)]
    report = {'status': 'failed', 'guest': 'not_run', 'sources': sources,
              'sdk_tree_sha256': sdk_hash, 'commands': [command], 'libc_linked': False}
    try:
        with (out / 'build.log').open('w') as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], check=True,
                           stdout=log, stderr=subprocess.STDOUT)
        if binary.stat().st_size > 131072:
            raise ValueError('fixture exceeds ordinary loader bound')
        if sources != {name: sha(ROOT / name) for name in INPUTS} or sdk_hash != tree_receipt(sdk)[0]:
            raise ValueError('input changed during build')
        report.update(status='built_not_run', artifacts={binary.name: sha(binary)}, toolchain=audit())
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS P1-B fixture build')


if __name__ == '__main__':
    main()
