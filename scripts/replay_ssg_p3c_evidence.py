#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay selected independent checks from exported synthetic P3C evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def extract_checked(archive, destination, expected):
    raw = archive.read_bytes()
    if sha(raw) != expected:
        raise ValueError('archive digest mismatch')
    destination.mkdir()
    extracted = set();total = 0
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts or member.name in extracted:
                raise ValueError('unsafe archive member')
            total += member.size
            if total > 256 * 1024 * 1024:
                raise ValueError('archive exceeds replay bound')
            target = destination.joinpath(*path.parts);target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.extractfile(member).read());extracted.add(member.name)
    manifest = json.loads((destination / 'export-manifest.json').read_text())['members']
    if extracted - {'export-manifest.json'} != set(manifest):
        raise ValueError('archive member list mismatch')
    for name, item in manifest.items():
        if sha((destination / name).read_bytes()) != item['exported_sha256']:
            raise ValueError('exported member digest mismatch')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--scratch', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    scratch = a.scratch.resolve();build = (ROOT / 'build').resolve()
    if not scratch.is_relative_to(build) or scratch.exists():
        raise SystemExit('Choose a fresh replay directory under build/')
    scratch.mkdir(parents=True)
    index = json.loads((a.evidence / 'export-index.json').read_text())
    report = {'status': 'FAILED', 'checks': [], 'scope': 'host replay of exported synthetic evidence; no guest execution'}
    environment = dict(os.environ);environment['PYTHONPATH'] = str(ROOT / 'tests')
    def check(name, command):
        result = subprocess.run([str(x) for x in command], cwd=ROOT, env=environment, capture_output=True)
        (scratch / (name + '.log')).write_bytes(result.stdout + result.stderr)
        report['checks'].append({'name': name, 'exit_code': result.returncode})
        if result.returncode:
            raise ValueError('replay check failed: ' + name)
    try:
        for name, item in index['archives'].items():
            extract_checked(a.evidence / (name + '.tar.gz'), scratch / name, item['sha256'])
        validation = scratch / 'validation'
        for name in ('baseline', 'edit', 'scroll', 'reload', 'revoke', 'protect-document', 'protect-ancestor', 'browser-exit', 'notes-exit', 'stop'):
            check('validation-' + name, [sys.executable, ROOT / 'tests/ssg_watch_verify.py', validation / name, '--require-structured'])
        check('validation-timeout', [sys.executable, ROOT / 'tests/ssg_watch_timeout_verify.py', validation / 'notes-timeout'])
        check('validation-cancel', [sys.executable, ROOT / 'tests/ssg_watch_cancel_verify.py', validation / 'cancel-inflight'])
        check('validation-ordinary', [sys.executable, ROOT / 'tests/ssg_watch_nondiagnostic_verify.py', validation / 'ordinary', '--require-structured'])
        contract = json.loads((validation / 'contract/report.json').read_text())
        if contract.get('status') != 'PASSED_SCOPED' or len(contract.get('checks', [])) != 32:
            raise ValueError('contract evidence mismatch')
        report['checks'].append({'name': 'validation-contract', 'exit_code': 0})
        caps = scratch / 'capped-faults'
        for name in ('cap-retry', 'cap-persistent'):
            check('capped-' + name, [sys.executable, ROOT / 'tests/ssg_watch_capped_verify.py', caps / name, '--require-noise'])
        compatibility = scratch / 'compatibility'
        for name in ('edit', 'revoke', 'protect-document', 'protect-ancestor'):
            check('compatibility-' + name, [sys.executable, ROOT / 'tests/ssg_p3b_dynamic_verify.py', compatibility / name,
                  '--browser-receipt', compatibility / name / 'browser.receipt.json'])
        check('compatibility-ordinary', [sys.executable, ROOT / 'tests/ssg_p3b_ordinary_verify.py', compatibility / 'ordinary-sample'])
        stress = scratch / 'stress';summary = json.loads((stress / 'summary.json').read_text())
        if summary.get('status') != 'PASSED_SCOPED' or summary.get('passed_runs') != 24 or summary.get('failed_runs') != 0:
            raise ValueError('stress summary mismatch')
        if sha((ROOT / 'tests/ssg_watch_verify.py').read_bytes()) != summary['verifier_sha256']:
            raise ValueError('stress verifier digest mismatch')
        for index in range(1, 25):
            check('stress-%02d' % index, [sys.executable, ROOT / 'tests/ssg_watch_verify.py', stress / ('run-%02d' % index), '--require-structured'])
        prior = scratch / 'prior-stress';old_summary = json.loads((prior / 'summary.json').read_text())
        old_verifier = scratch / 'r7-verifier.py'
        old_verifier.write_bytes(subprocess.check_output(['git', 'show', '3852fed:tests/ssg_watch_verify.py'], cwd=ROOT))
        if sha(old_verifier.read_bytes()) != old_summary['verifier_sha256']:
            raise ValueError('historical verifier digest mismatch')
        for index in range(1, 25):
            name = 'run-%02d' % index
            if index == 9:
                check('prior-stress-partial', [sys.executable, ROOT / 'tests/ssg_watch_incomplete_verify.py', prior / name])
            else:
                check('prior-stress-%02d' % index, [sys.executable, old_verifier, prior / name, '--require-structured'])
        comparison = scratch / 'performance/comparison.json'
        expected_comparison = json.loads(comparison.read_text())
        replayed = scratch / 'performance-replayed.json'
        check('performance', [sys.executable, ROOT / 'tests/ssg_watch_perf_compare.py', '--p3b', scratch / 'performance/p3b',
              '--watch', scratch / 'performance/watch', '--output', replayed])
        if json.loads(replayed.read_text()) != expected_comparison:
            raise ValueError('performance replay differs')
        for name in ('failure-watch-shutdown', 'failure-legacy-shutdown'):
            failed = json.loads((scratch / name / 'report.json').read_text())
            if failed.get('status') != 'FAILED' or failed.get('supervisor_exit', {}).get('code') != 1 or not failed.get('resources_restored'):
                raise ValueError('shutdown failure evidence mismatch')
        report['checks'].append({'name': 'preserved-shutdown-failures', 'exit_code': 0})
        interrupted = (scratch / 'failure-event-interleave/serial.log').read_bytes()
        lines = [line for line in interrupted.splitlines() if line.startswith(b'P3C_EVENT ')]
        valid = 0
        for line in lines:
            try:json.loads(line[len(b'P3C_EVENT '):]);valid += 1
            except (ValueError, UnicodeDecodeError):pass
        if len(lines) != 6 or valid >= 6 or b'P3C_WATCH_STOP reason=CYCLE_LIMIT cycles=3 events=6' not in interrupted:
            raise ValueError('interleaved event failure evidence mismatch')
        report['checks'].append({'name': 'preserved-event-interleaving', 'exit_code': 0})
        if 'regression_failures=0' not in (scratch / 'regressions/status.txt').read_text():
            raise ValueError('regression summary mismatch')
        report['checks'].append({'name': 'affected-regression-summary', 'exit_code': 0})
        report['status'] = 'PASSED_SCOPED'
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'], 'checks=', len(report['checks']), flush=True)
    return 0 if report['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
