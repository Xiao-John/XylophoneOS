#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a real stalled Notes request does not block later Browser observations."""
import json
from pathlib import Path
import re
import sys
from ssg_p3b_verify import frames, require, check_wiring, check_source_metadata
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt
from ssg_browser_structure import decode_capture
from ssg_watch_events import decode_event_records

out = Path(sys.argv[1])
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'notes-timeout' and report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'guest did not complete')
require(report['resources_restored'] and report['supervisor_exit'] == {'kind': 'exited', 'code': 0}, 'unclean shutdown')
serial = (out / 'serial.log').read_bytes()
require(b'SSG_TEST_PROVIDER_FAULT kind=TIMEOUT' in serial, 'fault did not occur')
data = frames(serial)
samples = [data[('aggregate', 'BASELINE', i)] for i in (1, 2, 3)]
sources = [{source['slot']: source for source in sample['sources']} for sample in samples]
check_wiring(serial, report, sources[0])
verify_browser_receipt(out / 'browser.receipt.json', report)
for sample, pair in zip(samples, sources):
    require(sample['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'atomic snapshot claimed')
    for source in pair.values(): check_source_metadata(source)
require([pair['notes']['status'] for pair in sources] == ['OBSERVED_COMPLETE', 'UNAVAILABLE', 'UNAVAILABLE'], 'timeout not isolated')
require(sources[1]['notes']['failure'] == 'TIMEOUT' and all('document' not in pair['notes'] for pair in sources[1:]), 'timed-out data published')
require(all(pair['browser']['status'] == 'OBSERVED_COMPLETE' for pair in sources), 'Browser stopped after Notes timeout')
event_records = decode_event_records(serial)
require(len({record['stream'] for record in event_records}) == 1, 'unexpected watch stream count')
events = [record['data'] for record in event_records]
require(len(events) == 6 and [e['event_type'] for e in events[::2]] == ['SOURCE_UNKNOWN', 'SOURCE_UNCHANGED', 'SOURCE_UNCHANGED'], 'Browser events')
require([e['event_type'] for e in events[1::2]] == ['SOURCE_UNKNOWN', 'SOURCE_UNAVAILABLE', 'SOURCE_UNAVAILABLE'], 'Notes events')
require(all(isinstance(e['identity_namespace'], dict) for e in events), 'structured namespace missing')
browser_q = sorted((seq, value) for (slot, direction, seq), value in data.items() if slot == 'browser' and direction == 'REQ')
browser_r = sorted((seq, value) for (slot, direction, seq), value in data.items() if slot == 'browser' and direction == 'RESP')
require([seq for seq, _ in browser_q] == [seq for seq, _ in browser_r], 'Browser frames unpaired')
groups = []
for (_, request), (_, response) in zip(browser_q, browser_r):
    if request['op'] == 'snapshot_begin': groups.append([])
    groups[-1].append((request, response))
oracles = decode_capture(serial)['oracles']
require(len(groups) == 3 and len(oracles) == 6, 'Browser observations or oracle missing')
for index, group in enumerate(groups):
    check_browser(group, oracles[2*index:2*index+2], sources[index]['browser'], report)
require(all([n for _, response in group for n in response['nodes']] ==
            [n for _, response in groups[0] for n in response['nodes']] for group in groups[1:]), 'Browser changed')
notes_q = sorted((seq, value) for (slot, direction, seq), value in data.items() if slot == 'notes' and direction == 'REQ')
notes_r = sorted((seq, value) for (slot, direction, seq), value in data.items() if slot == 'notes' and direction == 'RESP')
require(len(notes_q) == len(notes_r) + 1 and [x[0] for x in notes_q[:-1]] == [x[0] for x in notes_r], 'timeout request not preserved')
pairs = [(q, r) for (_, q), (_, r) in zip(notes_q, notes_r)]
note_groups = []
for pair in pairs:
    if pair[0].get('op') == 'snapshot':note_groups.append([])
    require(note_groups, 'missing Notes snapshot');note_groups[-1].append(pair)
capped = [group for group in note_groups if group[0][1].get('capped') is True]
require(all(len(group) == 1 for group in capped) and len(capped) == serial.count(b'P3C_NOTES_RETRY reason=CAPPED'), 'capped retries not accounted for')
complete = [group for group in note_groups if group[0][1].get('capped') is not True and
            any(response.get('remaining') == 0 for _, response in group[1:])]
require(len(complete) == 1, 'initial Notes transaction missing')
_, _, text, revision, failure = notes_segment(complete[0], report['processes']['notes'])
require(failure is None and text == (out / 'synthetic-input.txt').read_text() and revision == sources[0]['notes']['revision'], 'initial Notes baseline invalid')
require(samples[1]['status'] == samples[2]['status'] == 'AGGREGATE_PARTIAL', 'partial aggregate missing')
result = {'status': 'PASSED_SCOPED', 'scope': 'injected 30-second wire timeout with independently reread Browser peer',
          'cycles': 3, 'notes': ['complete', 'timeout', 'unavailable'], 'browser': ['initial', 'unchanged', 'unchanged'],
          'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'timeout-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
