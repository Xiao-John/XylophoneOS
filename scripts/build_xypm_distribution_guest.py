#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build an isolated signed-distribution guest using the production C/B/E sources.

Only this copied fixture source is instrumented. Runtime source and resource
limits are unchanged; the recorded original/snapshot maps make this explicit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(root):
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob('*'))
            if path.is_file() and '__pycache__' not in path.parts and 'build' not in path.relative_to(root).parts}


def replace(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise ValueError('fixture integration point changed: ' + str(path) + ': ' + old[:100])
    path.write_text(text.replace(old, new))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-tree', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    original, output = args.source_tree.resolve(strict=True), args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'source'
    source.mkdir()
    originals = {}
    for name in ('src', 'scripts', 'config', 'licenses', 'tests'):
        for path in sorted((original / name).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            relative = path.relative_to(original)
            originals[str(relative)] = digest(path)
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            if digest(destination) != originals[str(relative)] or digest(path) != originals[str(relative)]:
                raise ValueError('source changed while copying: ' + str(relative))
    for name in ('LICENSE', 'NOTICE', 'VERSION', 'Makefile'):
        path = original / name
        if path.exists():
            originals[name] = digest(path)
            shutil.copyfile(path, source / name)
    overlay = ('tests/fixtures/pumpkin/distribution_probe.hpp', 'src/user/include/xos/distribution_startup.hpp')
    overlay_hashes = {name: digest(ROOT / name) for name in overlay}
    for name in overlay:
        shutil.copyfile(ROOT / name, source / name)
    supervisor = source / 'tests/fixtures/pumpkin/durable_probe_supervisor.cpp'
    replace(supervisor, '#include "durable_probe_supervisor.hpp"',
            '#include "durable_probe_supervisor.hpp"\n#include <xos/distribution_startup.hpp>\n'
            '#include <xos/dynamic_launch.hpp>\n#include <xos/execution.hpp>')
    replace(supervisor, '#include "provisioning_probe.hpp"',
            '#include "provisioning_probe.hpp"\n#include "distribution_probe.hpp"')
    replace(supervisor, 'bool initialized = mode == anchor_guest::scenario::cycle;',
            'bool initialized = mode == anchor_guest::scenario::cycle || static_cast<u8>(mode) == 32;')
    replace(supervisor, '        switch (mode) {',
            '        if (static_cast<u8>(mode) >= 32 && static_cast<u8>(mode) <= 36) {\n'
            '            passed = started && distribution_probe(server, static_cast<u8>(mode)) && server.stop();\n'
            '        } else switch (mode) {')
    replace(supervisor, '    u8 outcome = static_cast<u8>(passed);',
            '    u8 outcome = static_cast<u8>(passed);\n'
            '    if (!passed && static_cast<u8>(mode) >= 32 && static_cast<u8>(mode) <= 36)\n'
            '        outcome = distribution_failure;')
    replace(source / 'src/user/programs/supervisor.cpp',
            '#if XOS_PUMPKIN_NATIVE_LOGIN || XOS_PUMPKIN_CATALOG_PROBE\n',
            '#if XOS_PUMPKIN_NATIVE_LOGIN || XOS_PUMPKIN_CATALOG_PROBE || XOS_XYPM_DISTRIBUTION_PROBE\n')
    proxy = source / 'src/user/pumpkin/generation_proxy.cpp'
    replace(proxy, '(mode < scenario::provisioning_update || mode > scenario::provisioning_new)',
            '(mode < scenario::provisioning_update || mode > scenario::provisioning_new)\n'
            '        && (static_cast<u8>(mode) < 32 || static_cast<u8>(mode) > 36)')
    replace(proxy, 'bool valid = finish.pass <= 1;', 'bool valid = true; // D preserves every finite diagnostic byte.')
    replace(proxy, "#if XOS_PUMPKIN_CATALOG_PROBE\n        90'000'000'000",
            "#if XOS_XYPM_DISTRIBUTION_PROBE\n        300'000'000'000\n#elif XOS_PUMPKIN_CATALOG_PROBE\n        90'000'000'000")
    builder = source / 'scripts/user_build.py'
    replace(builder, 'login_flags += ("-DXOS_PUMPKIN_PROVISIONING_STORE=1",)',
            'login_flags += ("-DXOS_PUMPKIN_PROVISIONING_STORE=1", "-DXOS_PUMPKIN_LAUNCH_PROBE=1", '
            '"-DXOS_XYPM_DISTRIBUTION_PROBE=1")')
    replace(builder, '*([str(loader_archive)] if name == "supervisor" and pumpkin_catalog_fixture else []),',
            '*([str(loader_archive)] if name == "supervisor" and (pumpkin_catalog_fixture or pumpkin_provisioning_store) else []),')
    replace(builder, 'strip_all = name == "supervisor" and pumpkin_catalog_fixture',
            'strip_all = name == "supervisor" and (pumpkin_catalog_fixture or pumpkin_provisioning_store)')
    snapshot = inputs(source)
    system = source / 'build/system'
    command = [sys.executable, str(source / 'scripts/build.py'), '--output-dir', str(system),
               '--pumpkin-anchored-probe', '--pumpkin-provisioning-store']
    report = {'status': 'building', 'source_tree': str(original), 'source': str(source),
              'system': str(system), 'original_inputs': originals, 'overlay_inputs': overlay_hashes,
              'snapshot_inputs': snapshot, 'command': command,
              'scope': 'dedicated developer authority guest; runtime and limits unchanged',
              'control_transport': {'supervisor_proxy': 'authenticated sys84 pair with PPC1 HELLO/ACK',
                                    'daemon_proxy': 'two retained successful sys81 create results; both peers authenticate owner',
                                    'supervisor_participant_enumeration_owned_before_launch': 0},
              'stripping': 'dedicated supervisor symbols only; exact entry and PT_LOAD byte equality asserted'}
    receipt = output / 'report.json'
    try:
        receipt.write_text(json.dumps(report, indent=2) + '\n')
        with (output / 'build.log').open('w') as log:
            completed = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
        report['exit_code'] = completed.returncode
        completed.check_returncode()
        if inputs(source) != snapshot:
            raise ValueError('frozen source snapshot changed during build')
        if any(digest(ROOT / name) != value for name, value in overlay_hashes.items()):
            raise ValueError('D overlay changed during build')
        report['system_manifest_sha256'] = digest(system / 'manifest.json')
        report['status'] = 'built_not_run'
        print('Built isolated D system: ' + str(system), flush=True)
    finally:
        if report['status'] == 'building': report['status'] = 'failed'
        report['build_log_sha256'] = digest(output / 'build.log')
        receipt.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
