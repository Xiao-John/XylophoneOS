#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recheck frozen E15 inputs and run real guest probes without replacing evidence.

Build core_lifecycle.cpp with src/ports/qt6/build_fixture.py first. This runner
reuses the recorded QtCore/SDK/image, verifies their hashes and source bindings,
and writes a separate report. It does not requalify a changed runtime or SDK.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--lifecycle', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    # Refuse to overwrite successful or failed raw evidence from a previous run.
    args.report_dir.mkdir(parents=True, exist_ok=False)
    report = {'status': 'FAILED', 'qualification_sha256': sha(args.qualification),
              'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'integrity': {}, 'tests': {}}
    try:
        q = read(args.qualification)
        for name, item in q['artifacts'].items():
            assert sha(ROOT / item['path']) == item['sha256'], name
            report['integrity'][name] = item['sha256']
        for name, expected in q['qt']['patch_and_runtime_sha256'].items():
            assert sha(ROOT / name) == expected, name
        image = ROOT / q['artifacts']['system_image']['path']
        sdk = (ROOT / q['artifacts']['threading_sdk_manifest']['path']).parent
        for folder, field in [(image.parent, 'sources'), (sdk, 'inputs')]:
            manifest = read(folder / 'manifest.json')
            for name, expected in manifest[field].items():
                assert sha(ROOT / name) == expected, name
            report['integrity'][folder.name + '_source_inputs'] = len(manifest[field])
        for name, expected in read(sdk / 'manifest.json')['artifacts'].items():
            assert sha(sdk / name) == expected, name
        build = image.parent.parent
        for name, expected in q['fixture_receipts'].items():
            receipt = build / (name + '.receipt.json')
            assert sha(receipt) == expected, name
            data = read(receipt)
            assert sha(Path(data['source'])) == data['source_sha256'], name
            assert sha(build / (name + '.elf')) == data['elf_sha256'], name
        lifecycle = args.lifecycle.resolve()
        receipt = read(lifecycle.with_suffix('.receipt.json'))
        assert sha(lifecycle) == receipt['elf_sha256']
        assert sha(Path(receipt['source'])) == receipt['source_sha256']
        assert receipt['qtcore_sha256'] == q['artifacts']['qtcore_archive']['sha256']
        assert receipt['sdk_manifest_sha256'] == q['artifacts']['threading_sdk_manifest']['sha256']
        report['lifecycle_receipt_sha256'] = sha(lifecycle.with_suffix('.receipt.json'))
        cases = [
            ('smoke-1', 'final_core_smoke', 'QT_CORE_SMOKE_OK', '', 'qt6_sdk_probe.py'),
            ('smoke-2', 'final_core_smoke', 'QT_CORE_SMOKE_OK', '', 'qt6_sdk_probe.py'),
            ('smoke-3', 'final_core_smoke', 'QT_CORE_SMOKE_OK', '', 'qt6_sdk_probe.py'),
            ('wake', 'final_wake_gate_v2', 'QT_WAKE_GATE_OK', '', 'qt6_sdk_probe.py'),
            ('events', 'final_core_events_v2', 'QT_EVENTS_OK', '', 'qt6_sdk_probe.py'),
            ('quota', 'final_core_events_v2', 'QT_THREAD_QUOTA_OK', 'quota', 'qt6_sdk_probe.py'),
            ('fault', 'final_core_events_v2', '', '', 'qt6_fault_probe.py'),
            ('persist', 'final_core_extended', '', '', 'qt6_persist_probe.py'),
            ('file-errors', 'final_core_extended', '', '', 'qt6_file_errors.py'),
            ('abi', 'final_core_abi', 'QT_ABI_OK', '', 'qt6_sdk_probe.py'),
            ('memory', 'final_core_memory', 'QT_MEMORY_SAMPLE_OK', '', 'qt6_sdk_probe.py'),
            ('mutex', 'qualified_mutex_contention', 'QT_MUTEX_CONTENTION_OK', '', 'qt6_sdk_probe.py'),
            ('interrupt', 'qualified_interrupt', 'QT_INTERRUPT_ONLY_OK', '', 'qt6_sdk_probe.py'),
        ] + [(f'lifecycle-{i}', None, 'QT_LIFECYCLE_OK', '', 'qt6_sdk_probe.py') for i in range(1, 4)]
        # The standalone wake probe has no build_fixture receipt; bind its ELF
        # directly to the previous guest receipt before executing it again.
        prior = read(args.qualification.parent / 'qualified-wake.json')
        assert sha(build / 'final_wake_gate_v2.elf') == prior['elf_sha256']
        for name, stem, marker, argument, runner in cases:
            payload = build / (stem + '.elf') if stem else lifecycle
            destination = args.report_dir / (name + '.json')
            cmd = [sys.executable, str(ROOT / 'tests' / runner), '--image', str(image),
                   '--payload', str(payload), '--report', str(destination)]
            if marker:
                cmd += ['--marker', marker]
            if argument:
                cmd += ['--argument', argument]
            with (args.report_dir / (name + '.runner.log')).open('wb') as log:
                result = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            data = read(destination) if destination.exists() else {}
            passed = result.returncode == 0 and data.get('status') == 'PASSED'
            report['tests'][name] = {'status': 'PASSED' if passed else 'FAILED',
                                      'runner_exit_code': result.returncode, 'command': cmd,
                                      'image_sha256': sha(image), 'elf_sha256': sha(payload)}
            print(name, report['tests'][name]['status'], flush=True)
        if all(item['status'] == 'PASSED' for item in report['tests'].values()):
            report['status'] = 'PASSED'
    finally:
        (args.report_dir / 'recheck.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'PASSED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
