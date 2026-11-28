#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Link the actual patched static loader against an exactly bound native SDK."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from sdk_receipt import sha, tree_receipt, verify_sdk
from shell_launch_support import bind_system
from toolchain import audit, tool

INPUTS = ('scripts/build_static_stdio_probe.py', 'tests/fixtures/static_stdio_compat/probe.cpp',
          'tests/fixtures/static_stdio_compat/target.cpp', 'src/user/loader/load.cpp',
          'src/user/loader/image_reader.hpp', 'scripts/sdk_receipt.py', 'scripts/toolchain.py',
          'tests/shell_launch_support.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system, source = args.system.resolve(strict=True), args.system_source.resolve(strict=True)
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'guest': 'not_run', 'commands': [],
              'sources': {name: sha(ROOT / name) for name in INPUTS}}
    try:
        manifest = bind_system(system, source)
        binding = verify_sdk(system / 'sdk', manifest)
        sdk = out / 'native_sdk_snapshot'
        shutil.copytree(system / 'sdk', sdk)
        require_tree = lambda: all(binding[key] == value for key, value in tree_receipt(sdk).items())
        if not require_tree(): raise ValueError('copied SDK differs')
        common = [tool('g++'), '-std=c++20', '-Os', '-g', '-Wall', '-Wextra', '-Werror',
                  '-Wconversion', '-Wshadow', '-ffreestanding', '-fno-exceptions', '-fno-rtti',
                  '-fno-threadsafe-statics', '-fno-use-cxa-atexit', '-fno-unwind-tables',
                  '-fno-asynchronous-unwind-tables', '-fno-stack-protector', '-fno-pic', '-fno-pie',
                  '-ffunction-sections', '-fdata-sections', '-mno-red-zone', '-mgeneral-regs-only',
                  '-nostdinc++', '-I', str(sdk / 'include'), '-nostdlib', '-static', '-no-pie',
                  '-Wl,--gc-sections,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                  '-T', str(sdk / 'user.ld'), str(sdk / 'crt0.o')]
        for name, marker in (('raw_stdio', 0), ('v3_stdio', 3), ('bad_marker', 2), ('static_stdio_probe', None)):
            binary = out / (name + '.elf')
            sources = [str(ROOT / INPUTS[2]), '-DEXEC_MARKER=' + str(marker)] if marker is not None else [
                str(ROOT / INPUTS[1]), str(ROOT / 'src/user/loader/load.cpp')]
            command = [*common, *sources, '-Wl,--start-group', str(sdk / 'lib/libxos.a'),
                       str(sdk / 'lib/libxos_loader.a'), '-Wl,--end-group', '-o', str(binary)]
            report['commands'].append(command)
            with (out / (name + '.log')).open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                subprocess.run([tool('objcopy'), '--strip-debug', str(binary)], stdout=log, stderr=subprocess.STDOUT, check=True)
            if binary.stat().st_size > 131072: raise ValueError('fixture exceeds native image bound')
            sections = subprocess.check_output([tool('readelf'), '-SW', str(binary)], text=True)
            if marker is not None and ('.xos.exec' in sections) != bool(marker):
                raise ValueError('actual native target marker differs')
        if (not require_tree() or verify_sdk(system / 'sdk', manifest) != binding or
                report['sources'] != {name: sha(ROOT / name) for name in INPUTS}):
            raise ValueError('source or SDK changed during compilation')
        report.update(status='built_not_run', system_build_id=manifest['build_id'],
                      system_manifest_sha256=sha(system / 'manifest.json'), native_sdk_binding=binding,
                      toolchain=audit(), artifacts={path.name: sha(path) for path in sorted(out.glob('*.elf'))},
                      loader_source='Actual production load.cpp explicitly linked before SDK archives; no loader/Files/kernel model.')
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
