#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a reference from an earlier real session is rejected after restart."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt
from ssg_browser_structure import decode_capture

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
p.add_argument('--previous', type=Path, required=True)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
verify_browser_receipt(out / 'browser.receipt.json', report)
require(report['case'] == 'old-instance', 'wrong case')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
previous = frames((a.previous / 'serial.log').read_bytes())[('aggregate', 'BASELINE', 0)]
current = f[('aggregate', 'BASELINE', 0)]
old = {s['slot']: s for s in previous['sources']}['browser']
now = {s['slot']: s for s in current['sources']}
for source in now.values(): check_source_metadata(source)
check_wiring(serial, report, now)
require(current['status'] == previous['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'sessions not complete')
require(report['old_instance'] == old['instance'] and old['instance'] != now['browser']['instance'], 'instance was reused')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((n, v) for (s, d, n), v in f.items() if s == slot and d == 'REQ')
    resp = sorted((n, v) for (s, d, n), v in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == [n for n, _ in resp] == list(range(1, len(req)+1)), 'unpaired frames')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
browser = records['browser']
old_request, refusal = browser[-1]
require(old_request.get('op') == 'detail' and old_request.get('sourceInstance') == old['instance'] and refusal.get('status') == 'SOURCE_REPLACED' and 'node' not in refusal, 'old instance was accepted')
oracles = decode_capture(serial)['oracles']
require(len(oracles) == 2, 'missing Browser oracle')
nodes, _ = check_browser(browser[:-1], oracles, now['browser'], report)
base, node, text, revision, failure = notes_segment(records['notes'], report['processes']['notes'])
expected = (out / 'synthetic-input.txt').read_text()
require(failure is None and text == expected and now['notes']['document']['text'] == expected, 'Notes mismatch')
require(b'P3B_OLD_INSTANCE status=SOURCE_REPLACED' in serial and report['resources_restored'], 'restart result/resources')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'browser_nodes': len(nodes), 'old_reference': 'SOURCE_REPLACED',
          'previous_instance_differs': True, 'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
