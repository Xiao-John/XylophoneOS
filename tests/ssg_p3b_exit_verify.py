#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check actual child exit mid-session and surviving independent source."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt
from ssg_browser_structure import decode_capture

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
verify_browser_receipt(out / 'browser.receipt.json', report)
case = report['case']
require(case in ('browser-exit', 'notes-exit'), 'wrong exit case')
require('real_ps2_' + case in report['events'] and report['qmp_events'], 'missing real input event')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in a['sources']} for a in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and a1['status'] == 'AGGREGATE_PARTIAL', 'invalid aggregate states')
require(a1['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED' and a1['semantics'] == 'sequential-per-source-non-atomic', 'snapshot semantics')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == list(range(1, len(req)+1)), 'request sequence')
    require([n for n, _ in resp] == list(range(1, len(resp)+1)), 'response sequence')
    require(len(req) == len(resp) + (1 if case == slot + '-exit' else 0), 'wrong unpaired request')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
oracles = decode_capture(serial)['oracles']
br = records['browser']
begins = [i for i, (q, _) in enumerate(br) if q.get('op') == 'snapshot_begin']
expected = (out / 'synthetic-input.txt').read_text()
if case == 'browser-exit':
    require(len(begins) == 1 and len(oracles) == 2, 'unexpected browser history')
    nodes, _ = check_browser(br, oracles, s0['browser'], report)
    require(s1['browser']['status'] == 'UNAVAILABLE' and 'nodes' not in s1['browser'], 'old Browser nodes reused')
    segments = []
    for pair in records['notes']:
        if pair[0].get('op') == 'snapshot': segments.append([])
        segments[-1].append(pair)
    require(len(segments) == 2, 'missing independent Notes reread')
    first, second = [notes_segment(x, report['processes']['notes']) for x in segments]
    require(first[2] == second[2] == expected and first[3] == second[3] and first[4] is None and second[4] is None, 'Notes reread changed')
    require(s1['notes']['document']['text'] == expected, 'surviving Notes omitted')
    require(b'P3B_DIFF browser=EXITED notes=UNCHANGED' in serial, 'exit isolation missing')
else:
    require(len(begins) == 2 and len(oracles) == 4, 'missing two browser captures')
    nodes, first_oracle = check_browser(br[:begins[1]], oracles[:2], s0['browser'], report)
    again, second_oracle = check_browser(br[begins[1]:], oracles[2:], s1['browser'], report)
    require(nodes == again and first_oracle['sourceEpoch'] == second_oracle['sourceEpoch'], 'Browser changed')
    nr = records['notes']
    starts = [i for i, (q, _) in enumerate(nr) if q.get('op') == 'snapshot']
    require(len(starts) == 2, 'missing interrupted Notes transaction')
    first = notes_segment(nr[:starts[1]], report['processes']['notes'])
    require(first[2] == expected and first[4] is None, 'initial Notes incomplete')
    staged = nr[starts[1]:]
    require(len(staged) >= 3 and staged[0][1]['status'] == 'OK', 'missing staged Notes data')
    prefix, revision, offset = '', None, 0
    for request, response in staged[1:]:
        require(request['op'] == 'text_range' and request['start'] == offset and response['status'] == 'OK', 'invalid staged range')
        if revision is None: revision = response['documentRevision']
        require(response['documentRevision'] == revision == first[3], 'mixed revision before exit')
        prefix += response['text']; offset = response['end']
    require(prefix and expected.startswith(prefix) and offset < len(expected.encode('utf-16-le')) // 2, 'Notes was not interrupted mid-read')
    require(s1['notes']['status'] == 'UNAVAILABLE' and 'document' not in s1['notes'], 'staged Notes data leaked after exit')
    require(b'P3B_DIFF browser=UNCHANGED notes=EXITED' in serial, 'exit isolation missing')
require(report['resources_restored'], 'resources not restored')
line = next((x for x in serial.splitlines() if x.startswith(b'P3B_AGGREGATE_DIFF ')), None)
expected_diff = {'status': 'OK', 'semantics': 'per-source-non-atomic',
                 'browser': 'INVALIDATED' if case == 'browser-exit' else 'UNCHANGED',
                 'notes': 'INVALIDATED' if case == 'notes-exit' else 'UNCHANGED'}
require(line and json.loads(line.split(b' ', 1)[1]) == expected_diff, 'aggregate Diff mismatch')
require(all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'child exit was not normal')
result = {'status': 'PASSED_SCOPED', 'case': case, 'browser_nodes': len(nodes), 'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
