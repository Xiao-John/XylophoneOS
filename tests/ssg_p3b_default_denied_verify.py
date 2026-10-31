#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that neither text scope is granted unless the session opts in."""
import argparse
import json
from pathlib import Path
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('output', type=Path)
a = p.parse_args()
out = a.output
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'default-denied', 'wrong case')
serial = (out / 'serial.log').read_bytes()
f = frames(serial)
aggregate = f[('aggregate', 'BASELINE', 0)]
sources = {v['slot']: v for v in aggregate['sources']}
require(set(sources) == {'browser', 'notes'}, 'missing source')
for source in sources.values():
    check_source_metadata(source)
check_wiring(serial, report, sources)
require(aggregate['status'] == 'AGGREGATE_PARTIAL' and aggregate['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'wrong aggregate status')
require(all(sources[slot]['status'] == 'DENIED' for slot in sources), 'default text scope was granted')
require('nodes' not in sources['browser'] and 'document' not in sources['notes'], 'restricted data in aggregate')
ordinary = report.get('ordinary_default_denied') is True
if ordinary:
    require(set(f) == {('aggregate', 'BASELINE', 0)} and b'SSG_ORACLE_BEGIN' not in serial,
            'ordinary run exposed diagnostics')
else:
    browser = f[('browser', 'RESP', 1)]
    require(browser.get('status') == 'DENIED' and 'nodes' not in browser, 'Browser response was not denied')
    note_requests = [v for (slot, direction, _), v in f.items() if slot == 'notes' and direction == 'REQ']
    note_responses = [v for (slot, direction, _), v in f.items() if slot == 'notes' and direction == 'RESP']
    require(len(note_requests) == len(note_responses) == 1 and note_requests[0].get('op') == 'snapshot', 'unexpected Notes transaction')
    nodes = note_responses[0].get('nodes', [])
    require(len(nodes) == 1 and nodes[0].get('textStatus') == 'NOT_AUTHORIZED' and 'text' not in nodes[0], 'Notes response exposed text')
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
    text = (out / 'synthetic-input.txt').read_text()
    chunks = [text[i:i+32] for i in range(0, len(text)-31, 32)]
    require(not any(chunk in value for value in strings(note_responses) for chunk in chunks),
            'synthetic document fragment leaked in Notes response')
require(report['resources_restored'] and len(report['source_exits']) == 2 and
        all('reaped=1 cancelled=0 outcome=1 code=0' in line for line in report['source_exits']), 'shutdown/resources')
result = {'status': 'OBSERVED' if ordinary else 'PASSED_SCOPED',
          'scope': 'ordinary output only' if ordinary else 'synthetic diagnostic build with separate captured IPC responses',
          'browser': 'DENIED', 'notes': 'DENIED', 'resources_restored': True,
          'source_exits': report['source_exits']}
(out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
