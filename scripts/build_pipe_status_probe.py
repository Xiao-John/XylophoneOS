#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the native pipe status probe from the exact matching exported SDK."""
import argparse
import json
from pathlib import Path
import subprocess
from toolchain import tool
from xos_app import tree_receipt
from xypm_format import sha_file

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('tests/fixtures/pipe_status_probe.cpp', 'scripts/build_pipe_status_probe.py',
          'src/shared/include/xos/process_abi.hpp', 'src/user/include/xos/sdk.hpp')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = {name: sha_file(ROOT / name) for name in INPUTS}
    for name in INPUTS[2:]:
        if sha_file(sdk / 'include/xos' / Path(name).name) != sources[name]:
            raise ValueError('SDK header differs: ' + name)
    command = [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
        '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
        '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-unwind-tables',
        '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
        '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++', '-I', str(sdk / 'include'),
        str(ROOT / INPUTS[0]), '-nostdlib', '-static', '-no-pie',
        '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
        '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), '-Wl,--start-group',
        str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group',
        '-o', str(out / 'pipe_status.elf')]
    with (out / 'build.log').open('w') as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run([tool('objcopy'), '--strip-debug', out / 'pipe_status.elf'], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    report = {'status': 'built_not_run', 'sources': sources, 'sdk_tree_sha256': tree_receipt(sdk)[0],
              'elf_sha256': sha_file(out / 'pipe_status.elf'), 'commands': [command]}
    (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS pipe status probe build')


if __name__ == '__main__':
    main()
