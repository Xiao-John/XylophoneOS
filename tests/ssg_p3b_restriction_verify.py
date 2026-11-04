#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify Browser denial leaves a separately authorized Notes source readable."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import notes_segment

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'browser-denied', 'wrong case')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
aggregate = f[('aggregate', 'BASELINE', 0)]
sources = {v['slot']: v for v in aggregate['sources']}
for source in sources.values(): check_source_metadata(source)
check_wiring(serial, report, sources)
require(aggregate['status'] == 'AGGREGATE_PARTIAL' and sources['browser']['status'] == 'DENIED' and 'nodes' not in sources['browser'], 'browser denial not isolated')
require(sources['notes']['status'] == 'OBSERVED_COMPLETE', 'Notes lost independent access')
require(aggregate['semantics'] == 'sequential-per-source-non-atomic' and aggregate['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'wrong snapshot semantics')
for sequence in (1, 2):
    req, resp = f[('browser', 'REQ', sequence)], f[('browser', 'RESP', sequence)]
    require(req.get('op') == 'snapshot_begin' and resp.get('status') == 'DENIED' and 'nodes' not in resp, 'browser refusal bypassed')
    require(resp.get('providerPid') == str(report['processes']['browser']), 'browser PID mismatch')
require(b'P3B_BROWSER_DENIAL_RECHECK refused=1 notes_alive=1' in serial, 'recheck marker missing')
reqs = sorted((seq, value) for (slot, direction, seq), value in f.items() if slot == 'notes' and direction == 'REQ')
resps = sorted((seq, value) for (slot, direction, seq), value in f.items() if slot == 'notes' and direction == 'RESP')
require([n for n, _ in reqs] == [n for n, _ in resps] == list(range(1, len(reqs)+1)), 'notes frames not paired')
base, node, text, revision, failure = notes_segment([(q, r) for (_, q), (_, r) in zip(reqs, resps)], report['processes']['notes'])
expected = (out / 'synthetic-input.txt').read_text()
require(failure is None and text == expected, 'Notes text differs')
notes = sources['notes']
require(notes['document']['text'] == expected and notes['revision'] == revision, 'aggregate Notes differs')
require(notes['document']['id'] == {'slot': 'notes', 'sourceInstance': base['sourceInstance'], 'sourceEpoch': base['sourceEpoch'], 'localNodeId': node['id']}, 'Notes identity mismatch')
units = len(expected.encode('utf-16-le')) // 2
digest = hashlib.sha256(expected.encode()).hexdigest().encode()
require(re.search(rb'SSG_TEST_OWNER_DOCUMENT units=' + str(units).encode() + rb' sha256=' + digest + rb'\b', serial), 'owner digest mismatch')
require(report['resources_restored'], 'resources not restored')
result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'browser_refusals': 2, 'notes_utf16_units': units, 'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
