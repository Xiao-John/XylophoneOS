#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the native R2 fixture from an anchored launcher's immutable approved roots."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from build_dynamic_launcher import anchor_sdk, sha
from sdk_receipt import tree_receipt
from toolchain import audit, tool

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ('scripts/build_dynamic_generation_probe.py', 'tests/fixtures/dynamic_generation_probe.cpp',
          'scripts/build_dynamic_launcher.py', 'scripts/sdk_receipt.py', 'scripts/toolchain.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher-build', type=Path, required=True)
    parser.add_argument('--sdk-manifest-sha256', required=True)
    parser.add_argument('--sdk-tree-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.launcher_build.resolve(strict=True)
    output = args.output.resolve()
    output.relative_to(ROOT / 'build')
    output.mkdir(parents=True, exist_ok=False)
    receipt = source / 'receipt.json'
    binding = json.loads(receipt.read_bytes())
    before = sha(receipt)
    report = {'status': 'failed', 'guest': 'not_run', 'commands': [], 'launcher_receipt_sha256': before}
    inputs = {name: sha(ROOT / name) for name in INPUTS}

    def validate():
        if (binding['status'] != 'built_not_run' or len(binding['approved_generations']) != 3 or
                binding['sdk_manifest_sha256'] != args.sdk_manifest_sha256 or
                binding['sdk_tree_sha256'] != args.sdk_tree_sha256):
            raise ValueError('fixture requires three explicit roots and the same independent SDK anchors')
        if anchor_sdk(source / 'sdk_snapshot', args.sdk_manifest_sha256, args.sdk_tree_sha256) != binding['c_sdk_binding']:
            raise ValueError('complete C SDK snapshot differs')
        for name, digest in binding['sources'].items():
            path = ROOT / name
            if Path(name).is_absolute() or '..' in Path(name).parts or sha(path) != digest:
                raise ValueError('launcher source differs: ' + name)
        for name, digest in binding['artifacts'].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or sha(source / name) != digest:
                raise ValueError('launcher artifact differs: ' + name)
        for item in binding['approved_generations']:
            name = item['snapshot']
            if Path(name).is_absolute() or '..' in Path(name).parts or sha(source / name) != item['sha256']:
                raise ValueError('approved generation snapshot differs')
        native = tree_receipt(source / 'native_sdk_snapshot')
        if any(binding['native_sdk_binding'][key] != value for key, value in native.items()):
            raise ValueError('complete native SDK snapshot differs')
        if sha(receipt) != before or inputs != {name: sha(ROOT / name) for name in INPUTS}:
            raise ValueError('fixture input changed')

    try:
        validate()
        shutil.copyfile(source / 'dynamic_roots.hpp', output / 'dynamic_roots.hpp')
        sdk = source / 'native_sdk_snapshot'
        binary = output / 'dynamic_generation.elf'
        command = [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
                   '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-unwind-tables',
                   '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
                   '-mno-red-zone', '-mgeneral-regs-only', '-nostdinc++', '-I', str(sdk / 'include'),
                   '-I', str(output), str(ROOT / INPUTS[1]), '-nostdlib', '-static', '-no-pie',
                   '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                   '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o'), '-Wl,--start-group',
                   str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)]
        report['commands'].append(command)
        with (output / 'compile.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        strip = [tool('objcopy'), '--strip-debug', str(binary)]
        report['commands'].append(strip)
        subprocess.run(strip, check=True)
        if binary.stat().st_size > 131072:
            raise ValueError('fixture exceeds ordinary native loader bound')
        validate()
        if sha(output / 'dynamic_roots.hpp') != binding['artifacts']['dynamic_roots.hpp']:
            raise ValueError('copied approved root header changed')
        report.update(status='built_not_run', sources=inputs, approved_generations=binding['approved_generations'],
                      sdk_manifest_sha256=args.sdk_manifest_sha256, sdk_tree_sha256=args.sdk_tree_sha256,
                      native_system_build_id=binding['native_system_build_id'],
                      native_sdk_tree_sha256=binding['native_sdk_binding']['tree_sha256'], toolchain=audit(),
                      artifacts={binary.name: sha(binary), 'dynamic_roots.hpp': sha(output / 'dynamic_roots.hpp')})
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
