#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check both real providers reject the other source's active pipe tokens."""
import argparse
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt
from ssg_browser_structure import decode_capture

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
verify_browser_receipt(out / 'browser.receipt.json', report)
require(report['case'] == 'pipe-isolation', 'wrong case')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in sample['sources']} for sample in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == a1['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'observations incomplete')
tokens = re.search(rb'P3B_TEST_TOKENS browser_read=(\d+) browser_write=(\d+) notes_read=(\d+) notes_write=(\d+)', serial)
require(tokens and len(set(tokens.groups())) == 4 and all(int(v) >= 65536 for v in tokens.groups()), 'tokens not distinct')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == [n for n, _ in resp] == list(range(1, len(req)+1)), 'unpaired frames')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
indices = {}
for slot, expected in (('browser', tokens.groups()[2:4]), ('notes', tokens.groups()[0:2])):
    indexes = [i for i, (q, _) in enumerate(records[slot]) if q.get('op') == 'test_pipe_isolation']
    require(len(indexes) == 1, 'missing cross-source test')
    indices[slot] = indexes[0]
    request, response = records[slot][indexes[0]]
    require((request.get('foreignRead'), request.get('foreignWrite')) == tuple(x.decode() for x in expected), 'wrong foreign endpoints')
    require(response.get('status') == 'OK' and response.get('readDenied') is True and response.get('writeDenied') is True and response.get('providerPid') == str(report['processes'][slot]) and response.get('sourceInstance') == s0[slot]['instance'], 'foreign pipe was not denied')
    require('text' not in response and 'nodes' not in response, 'probe returned document data')
br = records['browser']
oracles = decode_capture(serial)['oracles']
require(len(oracles) == 4, 'missing independent Browser references')
first, old = check_browser(br[:indices['browser']], oracles[:2], s0['browser'], report)
second, new = check_browser(br[indices['browser']+1:], oracles[2:], s1['browser'], report)
require(first == second and old['sourceEpoch'] == new['sourceEpoch'], 'Browser changed after probe')
nr = records['notes']
first_note = notes_segment(nr[:indices['notes']], report['processes']['notes'])
second_note = notes_segment(nr[indices['notes']+1:], report['processes']['notes'])
expected = (out / 'synthetic-input.txt').read_text()
require(first_note[2] == second_note[2] == expected and first_note[3] == second_note[3] and first_note[4] is None and second_note[4] is None, 'Notes changed after probe')
require(b'P3B_PIPE_CROSS_DENIAL browser=1 notes=1 browser_after=1 notes_after=1' in serial, 'cross-source denial marker missing')
require(b'P3B_STALE_TOKEN_REFUSED checked=4 denied=4 reused=0' in serial, 'stale token check missing')
line = next((x for x in serial.splitlines() if x.startswith(b'P3B_AGGREGATE_DIFF ')), None)
require(line and json.loads(line.split(b' ', 1)[1]) == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'UNCHANGED', 'notes': 'UNCHANGED'}, 'aggregate Diff mismatch')
require(report['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'foreign_read_write_denials': 4,
          'stale_token_denials': 4, 'browser_nodes_each': [len(first), len(second)],
          'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
