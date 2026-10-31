#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only verification of recorded regressions; does not execute guest tests."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runs-root', type=Path, default=ROOT / 'build/ssg_p2f_runs')
parser.add_argument('--output', type=Path, default=Path(__file__).with_name('regression-audit.json'))
args = parser.parse_args()
RUNS = args.runs_root
BASE = '9a739c7052d66dd75c0a0aceb807b0e4aa2fc16f'
sha = lambda data: hashlib.sha256(data).hexdigest()
result = {'not_a_new_guest_run': True, 'base_commit_for_assertion_comparison': BASE,
          'auditor_script_sha256': sha(Path(__file__).read_bytes()), 'unchanged_tests': {}}
for name in ('ssg_ipc_guest.py', 'aurora_platform_guest.py'):
    relative = 'tests/' + name
    before = subprocess.check_output(['git', 'show', BASE + ':' + relative], cwd=ROOT)
    current = (ROOT / relative).read_bytes()
    assert before == current, relative
    result['unchanged_tests'][relative] = sha(current)

p1_dir = RUNS / 'p1-regression-01'
p1 = json.loads((p1_dir / 'report.json').read_bytes())
p1_serial = (p1_dir / 'guest_serial.log').read_bytes()
assert p1['status'] == 'PASSED_SCOPED' and len(p1['checks']) == 16
assert len(p1['consumer_checks']) == 17 and all(row['status'] == 'PASS' for row in p1['consumer_checks'])
checks = re.findall(rb'^SSG_CONSUMER_CHECK ([^\r\n=]+)=(PASS|FAIL)\r?$', p1_serial, re.M)
assert len(checks) == 25 and all(status == b'PASS' for _, status in checks)
assert p1['final_resources'] == p1['baseline_resources'] == [130279, 2, 0]
for entry in p1['inputs'].values():
    expanded = os.path.expandvars(entry['path'])
    assert not re.search(r'\$\{XOS_[A-Z0-9_]+\}', expanded), 'Set the XOS path variables before checking inputs'
    assert sha(Path(expanded).read_bytes()) == entry['sha256']
for entry in p1['frames'] + p1['browser_frames']:
    data = (p1_dir / entry['file']).read_bytes()
    assert sha(data) == entry['sha256'] and len(data) == entry['bytes']
result['p1'] = {'status': p1['status'], 'outer_checks': len(p1['checks']),
                'Notes_Consumer_checks': 17, 'Browser_Consumer_checks': 8,
                'checks': p1['checks'], 'serial_sha256': sha(p1_serial),
                'final_resources': p1['final_resources']}

large_dir = RUNS / 'large-regression-01'
large = json.loads((large_dir / 'report.json').read_bytes())
large_serial = (large_dir / 'serial.log').read_bytes()
assert large['status'] == 'PASSED' and len(large['checks']) == 7
assert all(row['status'] == 'PASSED' for row in large['checks'])
snapshots = [json.loads(row) for row in re.findall(rb'^SSG_BROWSER_SNAPSHOT ([^\r\n]+)', large_serial, re.M)]
diffs = [json.loads(row) for row in re.findall(rb'^SSG_BROWSER_DIFF ([^\r\n]+)', large_serial, re.M)]
assert any(row.get('status') == 'OK' and row.get('capped') is False and row.get('changed')
           and row.get('metadata', {}).get('scrollY', 0) > 0 for row in diffs)
assert large['image_sha256'] == p1['inputs']['image']['sha256']
assert large['elf_sha256']['browser'] == p1['inputs']['browser']['sha256']
for name, index in (('first', 0), ('bottom', 2), ('reload', 3)):
    assert json.loads((large_dir / (name + '.json')).read_bytes()) == snapshots[index]
resources = [list(map(int, row)) for row in re.findall(
    rb'\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)', large_serial)]
assert resources[0] == resources[-1] == [130279, 2, 0]
result['legacy_nonpaged_browser'] = {
    'status': large['status'], 'outer_checks': len(large['checks']), 'checks': large['checks'],
    'serial_sha256': sha(large_serial), 'resource_observations': resources,
    'snapshots': [{'source_epoch': row['sourceEpoch'], 'capped': row['capped'],
                   'cap_reason': row['diagnostics']['capReason'], 'nodes': len(row['nodes']),
                   'scrollY': row['metadata']['scrollY']} for row in snapshots],
    'diffs': [{'status': row['status'], 'capped': row.get('capped'),
               'changed_nodes': len(row.get('changed', [])),
               'scrollY': row.get('metadata', {}).get('scrollY')} for row in diffs],
    'limitation': 'Current original assertions passed. The first snapshot was still TIME-capped; '
                  'later complete snapshots and scrolling Diff passed. This does not establish '
                  'that the nonpaged 30 ms cap can never truncate a query.'}
output = args.output
output.write_text(json.dumps(result, indent=2) + '\n')
print('P1: 16 outer checks, 17 Notes + 8 Browser Consumer checks, PASSED_SCOPED')
print('Legacy nonpaged Browser: 7 checks, PASSED, original scripts byte-identical to baseline')
