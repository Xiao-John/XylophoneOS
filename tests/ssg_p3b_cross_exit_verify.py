#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a source dying during its peer's transaction invalidates the sample."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt, verify_qmp_key
from ssg_browser_structure import decode_capture, validate_oracle, compare_structure

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'browser-exit-during-notes' and 'real_ps2_browser-exit-during-notes' in report['events'], 'missing input')
verify_browser_receipt(out / 'browser.receipt.json', report)
serial = (out / 'serial.log').read_bytes()
verify_qmp_key(report, serial, b'P3B_EDIT_INJECTION_READY', 'esc', b'[task] event=reclaimed pid=' + str(report['processes']['browser']).encode())
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in sample['sources']} for sample in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and a1['status'] == 'AGGREGATE_PARTIAL', 'source death produced incorrect global completeness')
require(s1['browser']['status'] == 'UNAVAILABLE' and 'nodes' not in s1['browser'] and s1['browser']['epoch'] is None, 'dead Browser was republished')
require(s1['notes']['status'] == 'OBSERVED_COMPLETE', 'surviving Notes not retained')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == [n for n, _ in resp] == list(range(1, len(req)+1)), 'unpaired frames')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
br = records['browser']
starts = [i for i, (q, _) in enumerate(br) if q.get('op') == 'snapshot_begin']
oracles = decode_capture(serial)['oracles']
require(len(starts) == 2 and len(oracles) == 4, 'missing two Browser traversals')
first, before = check_browser(br[:starts[1]], oracles[:2], s0['browser'], report)
second_before, second_after = [v['data'] for v in oracles[2:]]
reference = validate_oracle(second_before, report['inputs']['input']['sha256'], 'before')
validate_oracle(second_after, report['inputs']['input']['sha256'], 'after')
for key in ('document','inputSha256','sourceInstance','providerPid','sourceEpoch','sourceRevision','nodeCount','structureSha256','nodes'):
    require(second_before[key] == second_after[key], 'second Browser oracle changed')
require(second_before['sourceInstance'] == before['sourceInstance'] and second_before['sourceEpoch'] == before['sourceEpoch'], 'second Browser identity')
cursor = None
nodes = []
session = None
for i, (request, response) in enumerate(br[starts[1]:]):
    require(request.get('op') == ('snapshot_begin' if i == 0 else 'snapshot_next'), 'second Browser operation')
    if i: require(request.get('cursor') == cursor and request.get('sourceInstance') == before['sourceInstance'], 'second cursor chain')
    require(response.get('status') == 'OK' and response.get('pageSequence') == str(i+1), 'second page failed')
    if session is None: session = response.get('sessionId')
    require(session and response.get('sessionId') == session and response.get('sourceValid') is True and
            response.get('query') == '' and response.get('visibleOnly') is False, 'mixed or invalid second Browser session')
    complete = i == len(br[starts[1]:]) - 1
    require(response.get('complete') is complete and response.get('traversalComplete') is complete and response.get('hasNext') is (not complete), 'second traversal completion')
    for key in ('sourceInstance','sourceEpoch','sourceRevision','providerPid'):
        require(response.get(key) == second_before[key], 'second page source mismatch')
    cursor = response['cursor']; nodes.extend(response['nodes'])
require(br[-1][1].get('complete') is True and cursor == '', 'second Browser traversal incomplete')
compare_structure(reference, nodes)
last_browser_sequence = max(seq for (slot, direction, seq) in f if slot == 'browser' and direction == 'RESP')
last_browser_end = serial.find(('P3B_FRAME_END browser RESP ' + str(last_browser_sequence)).encode())
require(0 <= last_browser_end < serial.find(b'P3B_EDIT_INJECTION_READY'), 'Browser traversal did not finish before the Notes read was interrupted')
segments = []
for pair in records['notes']:
    if pair[0].get('op') == 'snapshot': segments.append([])
    segments[-1].append(pair)
require(len(segments) == 2, 'missing Notes samples')
first_note, second_note = [notes_segment(s, report['processes']['notes']) for s in segments]
expected = (out / 'synthetic-input.txt').read_text()
require(first_note[2] == second_note[2] == expected and first_note[3] == second_note[3] and first_note[4] is None and second_note[4] is None, 'Notes changed')
require(s1['notes']['document']['text'] == expected, 'surviving Notes missing')
line = next((x for x in serial.splitlines() if x.startswith(b'P3B_AGGREGATE_DIFF ')), None)
require(line and json.loads(line.split(b' ', 1)[1]) == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'INVALIDATED', 'notes': 'UNCHANGED'}, 'aggregate Diff mismatch')
require(b'P3B_CROSS_EXIT browser=UNAVAILABLE notes=OBSERVED_COMPLETE' in serial and report['resources_restored'], 'failure was not contained')
require(all('reaped=1 cancelled=0 outcome=1 code=0' in x for x in report['source_exits']), 'children did not exit normally')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'earlier_browser_nodes': len(nodes),
          'result': 'AGGREGATE_PARTIAL', 'browser': 'UNAVAILABLE', 'notes': 'OBSERVED_COMPLETE',
          'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
