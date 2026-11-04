#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the ordinary three-program run without claiming a DOM Oracle."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'ordinary', 'wrong case')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
require(set(f) == {('aggregate', 'BASELINE', 0)} and b'SSG_ORACLE_BEGIN' not in serial, 'ordinary run emitted diagnostic frames or oracle')
aggregate = f[('aggregate', 'BASELINE', 0)]
sources = {v['slot']: v for v in aggregate['sources']}
for source in sources.values(): check_source_metadata(source)
check_wiring(serial, report, sources)
require(aggregate['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and aggregate['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'aggregate status')
notes = sources['notes']['document']
expected = (out / 'synthetic-input.txt').read_text()
require(notes['text'] == expected and notes['utf16Units'] == len(expected.encode('utf-16-le')) // 2, 'Notes content')
browser = sources['browser']
require(len(browser['nodes']) == 267 and browser['nodes'][0]['tag'] == 'html', 'Browser observation')
require(all(n['id']['slot'] == 'browser' and n['id']['sourceInstance'] == browser['instance'] and n['id']['sourceEpoch'] == browser['epoch'] for n in browser['nodes']), 'Browser namespace')
require(report['resources_restored'] and all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
result = {'status': 'OBSERVED', 'scope': 'ordinary supervisor, ordinary Browser and ordinary Notes; no raw IPC or independent DOM Oracle in this run',
          'browser_nodes': len(browser['nodes']), 'notes_utf16_units': notes['utf16Units'], 'resources_restored': True,
          'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
