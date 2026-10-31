#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify document epoch replacement and continued Notes observation."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_qmp_key, verify_browser_receipt
from ssg_browser_structure import decode_capture

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
verify_browser_receipt(out / 'browser.receipt.json', report)
require(report['case'] == 'browser-reload' and 'real_ps2_browser-reload' in report['events'], 'missing reload input')
serial = (out / 'serial.log').read_bytes()
verify_qmp_key(report, serial, b'P3B_BROWSER_RELOAD_READY', 'r', b'BROWSER_LOADED path=')
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in a['sources']} for a in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == a1['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and a1['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'aggregate state')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == [n for n, _ in resp] == list(range(1, len(req)+1)), 'unpaired frames')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
br = records['browser']
refs = [i for i, (q, _) in enumerate(br) if q.get('op') == 'detail']
require(len(refs) == 1, 'old reference request missing')
i = refs[0]
oracles = decode_capture(serial)['oracles']
require(len(oracles) == 4, 'missing two oracle pairs')
old_nodes, old = check_browser(br[:i], oracles[:2], s0['browser'], report)
new_nodes, new = check_browser(br[i+1:], oracles[2:], s1['browser'], report)
req, resp = br[i]
require(req.get('sourceInstance') == old['sourceInstance'] and req.get('sourceEpoch') == old['sourceEpoch'] and resp.get('status') == 'SOURCE_REPLACED', 'old node reference accepted')
require(old['sourceInstance'] == new['sourceInstance'] and old['sourceEpoch'] != new['sourceEpoch'], 'source epoch did not change')
require(old_nodes == new_nodes, 'same fixture structure differs')
require(s0['browser']['nodes'][0]['id'] != s1['browser']['nodes'][0]['id'], 'new epoch reused old composite identity')
segments = []
for pair in records['notes']:
    if pair[0].get('op') == 'snapshot': segments.append([])
    segments[-1].append(pair)
require(len(segments) == 2, 'missing Notes reread')
first, second = [notes_segment(segment, report['processes']['notes']) for segment in segments]
expected = (out / 'synthetic-input.txt').read_text()
require(first[2] == second[2] == expected and first[3] == second[3] and first[4] is None and second[4] is None, 'Notes changed during Browser replacement')
require(s1['notes']['document']['text'] == expected, 'Notes missing from second aggregate')
require(b'P3B_DIFF browser=REPLACED notes=UNCHANGED old_reference=SOURCE_REPLACED' in serial, 'replacement result missing')
line = next((x for x in serial.splitlines() if x.startswith(b'P3B_AGGREGATE_DIFF ')), None)
require(line and json.loads(line.split(b' ', 1)[1]) == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'REPLACED', 'notes': 'UNCHANGED'}, 'aggregate Diff mismatch')
require(report['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'browser_nodes_each': [len(old_nodes), len(new_nodes)],
          'old_reference': 'SOURCE_REPLACED', 'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
