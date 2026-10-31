#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check owner revocation removes Browser data while Notes remains readable."""
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
require(report['case'] == 'browser-revoke' and 'real_ps2_browser-revoke' in report['events'], 'missing owner input')
serial = (out / 'serial.log').read_bytes()
verify_qmp_key(report, serial, b'P3B_BROWSER_REVOKE_READY', '9', b'SSG_TEST_BROWSER_REVOKED')
f = frames(serial)
a0, a1 = [f[('aggregate', 'BASELINE', i)] for i in (0, 1)]
s0, s1 = [{v['slot']: v for v in a['sources']} for a in (a0, a1)]
for sample in (s0, s1):
    for source in sample.values(): check_source_metadata(source)
check_wiring(serial, report, s0)
require(a0['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and a1['status'] == 'AGGREGATE_PARTIAL', 'invalid aggregate states')
require(s1['browser']['status'] == 'DENIED' and 'nodes' not in s1['browser'], 'revoked Browser nodes were reused')
require(s1['notes']['status'] == 'OBSERVED_COMPLETE', 'Notes became unavailable')
records = {}
for slot in ('browser', 'notes'):
    req = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'REQ')
    resp = sorted((seq, value) for (s, d, seq), value in f.items() if s == slot and d == 'RESP')
    require([n for n, _ in req] == [n for n, _ in resp] == list(range(1, len(req)+1)), 'unpaired requests')
    records[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
br = records['browser']
require(len(br) > 3 and all(q.get('op') == 'snapshot_begin' and r.get('status') == 'DENIED' and 'nodes' not in r for q, r in br[-3:-1]), 'Browser denial/retry missing')
oracles = decode_capture(serial)['oracles']
require(len(oracles) == 2, 'test oracle emitted after revocation or missing before revocation')
nodes, old = check_browser(br[:-3], oracles, s0['browser'], report)
for _, resp in br[-3:]:
    require(resp.get('sourceInstance') == old['sourceInstance'] and resp.get('providerPid') == str(report['processes']['browser']), 'denial source mismatch')
require(br[-1][0].get('op') == 'detail' and br[-1][0].get('sourceEpoch') == old['sourceEpoch'] and br[-1][1].get('status') == 'DENIED' and 'node' not in br[-1][1], 'old reference bypassed revocation')
segments = []
for pair in records['notes']:
    if pair[0].get('op') == 'snapshot': segments.append([])
    segments[-1].append(pair)
require(len(segments) == 2, 'missing independent Notes reread')
first, second = [notes_segment(segment, report['processes']['notes']) for segment in segments]
expected = (out / 'synthetic-input.txt').read_text()
require(first[2] == second[2] == expected and first[3] == second[3] and first[4] is None and second[4] is None, 'Notes changed or failed')
require(s1['notes']['document']['text'] == expected, 'Notes data missing')
require(b'SSG_TEST_BROWSER_REVOKED' in serial and b'P3B_DIFF browser=DENIED notes=UNCHANGED retry_refused=1' in serial, 'revocation result missing')
require(b'P3B_BROWSER_OLD_REF_AFTER_REVOKE status=DENIED' in serial, 'old reference refusal missing')
line = next((x for x in serial.splitlines() if x.startswith(b'P3B_AGGREGATE_DIFF ')), None)
require(line and json.loads(line.split(b' ', 1)[1]) == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'PERMISSION_CHANGED', 'notes': 'UNCHANGED'}, 'aggregate Diff mismatch')
require(report['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'browser_nodes_before': len(nodes), 'browser_refusals': 3,
          'notes_utf16_units': len(expected.encode('utf-16-le')) // 2, 'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
