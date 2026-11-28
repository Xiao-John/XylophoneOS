#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build independent Mobius clients with one matching native or threading SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from toolchain import audit, tool
from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]
HEADERS = ('src/shared/include/xos/interactium_abi.hpp',
           'src/user/include/xos/interactium_client.hpp', 'src/user/include/xos/sdk.hpp',
           'src/shared/include/xos/process_abi.hpp', 'src/shared/include/xos/thread_abi.hpp')
INPUTS = ('tests/fixtures/mobius_multiwindow.cpp', 'scripts/build_mobius_multiwindow_probe.py', *HEADERS)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sdk, out = args.sdk.resolve(strict=True), args.output.resolve()
    out.relative_to(ROOT / 'build'); out.mkdir(parents=True, exist_ok=False)
    sources = {name: sha(ROOT / name) for name in INPUTS}
    for name in HEADERS:
        if sha(sdk / 'include/xos' / Path(name).name) != sources[name]:
            raise ValueError('SDK header differs: ' + name)
    sdk_hash = tree_receipt(sdk)[0]
    sdk_manifest = json.loads((sdk / 'manifest.json').read_bytes())
    threaded = sdk_manifest.get('profile') == 'xos-threading-v1-experimental'
    if sdk_manifest.get('profile') and not threaded:
        raise ValueError('unsupported SDK profile')
    if threaded:
        for path, digest in sdk_manifest['artifacts'].items():
            if sha(sdk / path) != digest:
                raise ValueError('threading SDK artifact differs: ' + path)
    crt = 'crt0_posix.o' if threaded else 'crt0.o'
    libraries = ['lib/libxos.a', 'lib/libc.a', 'lib/libm.a'] if threaded else ['lib/libxos.a']
    profile_flags = ['-ftls-model=local-exec', '-DXOS_THREADED_RUNTIME',
                     '-D_POSIX_C_SOURCE=200809L'] if threaded else []
    link_libraries = (['-Wl,--start-group', '-Wl,--whole-archive', str(sdk / libraries[0]),
                       '-Wl,--no-whole-archive', *[str(sdk / p) for p in libraries[1:]],
                       '-Wl,--end-group'] if threaded else [str(sdk / libraries[0])])
    binary = out / 'mobius_multiwindow.elf'
    command = [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
               '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
               '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-unwind-tables',
               '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
               '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++', *profile_flags,
               '-I', str(sdk / 'include'),
               str(ROOT / INPUTS[0]), '-nostdlib', '-static', '-no-pie',
               '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
               '-T', str(sdk / 'user.ld'), str(sdk / crt), *link_libraries, '-o', str(binary)]
    report = {'status': 'failed', 'guest': 'not_run', 'sources': sources,
              'sdk_tree_sha256': sdk_hash, 'commands': [command], 'libc_linked': threaded,
              'client_sdk_profile': 'threading_posix_newlib' if threaded else 'ordinary_native_no_libc',
              'runtime_inputs': {p: sha(sdk / p) for p in [crt, 'user.ld', *libraries]}}
    try:
        with (out / 'build.log').open('w') as log:
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
            subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], check=True,
                           stdout=log, stderr=subprocess.STDOUT)
        if binary.stat().st_size > 1024 * 1024:
            raise ValueError('fixture exceeds this test profile size bound')
        if sources != {name: sha(ROOT / name) for name in INPUTS} or sdk_hash != tree_receipt(sdk)[0]:
            raise ValueError('input changed during build')
        report.update(status='built_not_run', artifacts={binary.name: sha(binary)}, toolchain=audit())
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS Mobius fixture build')


if __name__ == '__main__':
    main()
