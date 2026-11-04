#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a test-only real-pipe stall/truncated response is contained."""
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
case = report['case']
require(case in ('notes-timeout', 'notes-truncated', 'notes-cancel'), 'wrong fault case')
kind = 'TIMEOUT' if case == 'notes-timeout' else 'TRUNCATED' if case == 'notes-truncated' else 'CANCELLED'
provider_kind = 'CANCEL_STALL' if case == 'notes-cancel' else kind
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in a['sources']} for a in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and a1['status'] == 'AGGREGATE_PARTIAL', 'bad aggregate status')
require(s1['notes']['status'] == 'UNAVAILABLE' and s1['notes']['failure'] == kind and 'document' not in s1['notes'], 'staged data leaked or fault mislabeled')
require(('SSG_TEST_PROVIDER_FAULT kind=' + provider_kind).encode() in serial and ('P3B_DIFF browser=UNCHANGED notes=' + kind).encode() in serial, 'fault marker missing')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == list(range(1, len(req)+1)) and [n for n, _ in resp] == list(range(1, len(resp)+1)), 'non-contiguous frame sequences')
    require(len(req) == len(resp) + (1 if slot == 'notes' else 0), 'unexpected unpaired frame')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
br = records['browser']
starts = [i for i, (q, _) in enumerate(br) if q.get('op') == 'snapshot_begin']
oracles = decode_capture(serial)['oracles']
require(len(starts) == 2 and len(oracles) == 4, 'missing Browser re-observation')
first, before = check_browser(br[:starts[1]], oracles[:2], s0['browser'], report)
second, after = check_browser(br[starts[1]:], oracles[2:], s1['browser'], report)
require(first == second and before['sourceEpoch'] == after['sourceEpoch'], 'independent Browser changed')
nr = records['notes']
starts = [i for i, (q, _) in enumerate(nr) if q.get('op') == 'snapshot']
require(len(starts) == 2, 'missing interrupted Notes transaction')
baseline = notes_segment(nr[:starts[1]], report['processes']['notes'])
expected = (out / 'synthetic-input.txt').read_text()
require(baseline[2] == expected and baseline[4] is None, 'initial Notes mismatch')
staged = nr[starts[1]:]
require(len(staged) >= 3, 'fault did not interrupt staged text')
prefix, offset = '', 0
for request, response in staged[1:]:
    require(request.get('op') == 'text_range' and request.get('start') == offset and response.get('status') == 'OK', 'invalid staged range')
    require(response.get('documentRevision') == baseline[3], 'mixed revisions')
    prefix += response['text']; offset = response['end']
require(expected.startswith(prefix) and offset < len(expected.encode('utf-16-le')) // 2, 'staging was not partial')
cancel_latency = None
if case == 'notes-cancel':
    requested = re.search(rb'P3B_CANCEL_WORKER requested_ns=(\d+)', serial)
    discarded = re.search(rb'P3B_NOTES_DISCARD reason=CANCELLED units=(\d+) observed_ns=(\d+)', serial)
    require(requested and discarded and int(discarded[1]) == offset and b'P3B_CANCEL_ARMED' in serial, 'cancellation did not discard staged data')
    cancel_latency = int(discarded[2]) - int(requested[1])
    require(0 <= cancel_latency <= 1000000000, 'cancellation was not bounded to one second')
require(report['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
line = next((x for x in serial.splitlines() if x.startswith(b'P3B_AGGREGATE_DIFF ')), None)
require(line and json.loads(line.split(b' ', 1)[1]) == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'UNCHANGED', 'notes': 'INVALIDATED'}, 'aggregate Diff mismatch')
result = {'status': 'PASSED_SCOPED', 'case': case, 'browser_nodes': len(first), 'discarded_utf16_units': offset,
          'cancel_latency_ns': cancel_latency, 'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
