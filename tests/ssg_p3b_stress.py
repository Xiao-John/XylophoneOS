#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Repeat complete synthetic guest sessions without deleting failed runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'browser-receipt', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--count', type=int, default=32)
    a = p.parse_args()
    if not 1 <= a.count <= 64:
        p.error('count must be between 1 and 64')
    out = a.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    result = {'status': 'RUNNING', 'target': a.count, 'runs': [],
              'scope': 'separate complete synthetic sessions, real guest, fixed input',
              'pipe_counter': 'UNAVAILABLE; four-pipe capacity probe is not an exact counter',
              'inputs_sha256': {name: sha(getattr(a, name)) for name in ('image', 'supervisor', 'browser', 'notes', 'input', 'browser_receipt')}}
    consecutive_failures = 0
    for i in range(1, a.count + 1):
        run = out / f'run-{i:02d}'
        command = [sys.executable, str(ROOT / 'tests/ssg_p3b_guest.py'), '--image', str(a.image),
                   '--supervisor', str(a.supervisor), '--browser', str(a.browser), '--notes', str(a.notes),
                   '--input', str(a.input), '--output', str(run)]
        started = time.monotonic()
        timed_out = False
        with (out / f'run-{i:02d}.console.log').open('wb') as log:
            proc = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=480)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    code = proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    code = proc.wait()
        verified = False
        if code == 0 and not timed_out:
            with (out / f'run-{i:02d}.verify.log').open('wb') as log:
                verified = subprocess.run([sys.executable, str(ROOT / 'tests/ssg_p3b_verify.py'), str(run),
                                           '--browser-receipt', str(a.browser_receipt)], cwd=ROOT,
                                          stdout=log, stderr=subprocess.STDOUT).returncode == 0
        report_file = run / 'report.json'
        report = json.loads(report_file.read_text()) if report_file.exists() else {}
        clean_exits = len(report.get('source_exits', [])) == 2 and all(
            'reaped=1 cancelled=0 outcome=1 code=0' in x for x in report.get('source_exits', []))
        good = (code == 0 and verified and report.get('resources_restored') is True and clean_exits and
                report.get('supervisor_exit') == {'kind': 'exited', 'code': 0} and
                (report.get('shutdown') or {}).get('clean') is True and
                report.get('pipe_capacity_probe') == 'P3B_PIPE_REUSE acquired=4 requested=4')
        item = {'run': i, 'status': 'PASSED' if good else 'FAILED', 'runner_exit': code, 'timeout': timed_out,
                'elapsed_seconds': round(time.monotonic() - started, 3),
                'supervisor_exit': report.get('supervisor_exit'), 'source_exits': report.get('source_exits', []),
                'active_display_resources': report.get('active_display'), 'after_resources': report.get('after'),
                'thread_samples': report.get('thread_samples', []), 'pipe_capacity_probe': report.get('pipe_capacity_probe'),
                'shutdown': report.get('shutdown'),
                'independent_check': 'PASSED' if verified else 'FAILED_OR_NOT_RUN'}
        result['runs'].append(item)
        consecutive_failures = 0 if good else consecutive_failures + 1
        result['status'] = 'RUNNING'
        (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        print(f'run {i}/{a.count}: {item["status"]}, {item["elapsed_seconds"]} s', flush=True)
        if consecutive_failures >= 3:
            result['stop_reason'] = 'three consecutive failed runs; preserved for diagnosis'
            break
    passed = sum(x['status'] == 'PASSED' for x in result['runs'])
    result['passed'] = passed
    result['status'] = 'PASSED_SCOPED' if passed == a.count else 'PARTIAL'
    (out / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['status'] == 'PASSED_SCOPED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
