#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a captured capped Notes observation and subsequent resynchronization."""
import hashlib
import json
from pathlib import Path
import re
import sys
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt
from ssg_browser_structure import decode_capture

out = Path(sys.argv[1])
report = json.loads((out / 'report.json').read_text())
require(report['case'] == 'scroll' and report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'guest did not complete')
require(report['resources_restored'] and report['supervisor_exit'] == {'kind': 'exited', 'code': 0}, 'unclean shutdown')
serial = (out / 'serial.log').read_bytes()
data = frames(serial)
samples = [data[('aggregate', 'BASELINE', i)] for i in (1, 2, 3)]
sources = [{source['slot']: source for source in sample['sources']} for sample in samples]
check_wiring(serial, report, sources[0]);verify_browser_receipt(out / 'browser.receipt.json', report)
for sample, pair in zip(samples, sources):
    require(sample['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'atomic snapshot claimed')
    for source in pair.values():check_source_metadata(source)
require([pair['notes']['status'] for pair in sources] == ['UNKNOWN', 'OBSERVED_COMPLETE', 'OBSERVED_COMPLETE'], 'unexpected Notes state')
require(sources[0]['notes']['failure'] == 'INVALID_SNAPSHOT' and 'document' not in sources[0]['notes'], 'partial snapshot was published')
events = [json.loads(value) for value in re.findall(rb'^P3C_EVENT (\{.*\})\r?$', serial, re.MULTILINE)]
require(len(events) == 6 and [event['event_type'] for event in events[1::2]] == ['SOURCE_UNKNOWN', 'RESET_REQUIRED', 'SOURCE_UNCHANGED'], 'Notes continuity not reset')
require([event['event_type'] for event in events[::2]] == ['SOURCE_UNKNOWN', 'SOURCE_CHANGED', 'SOURCE_CHANGED'], 'Browser changes missing')
require(samples[0]['status'] == 'AGGREGATE_PARTIAL' and samples[1]['status'] == samples[2]['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'aggregate recovery')

def paired(slot):
    requests = sorted((seq, value) for (s, direction, seq), value in data.items() if s == slot and direction == 'REQ')
    responses = sorted((seq, value) for (s, direction, seq), value in data.items() if s == slot and direction == 'RESP')
    require([seq for seq, _ in requests] == [seq for seq, _ in responses], 'unpaired source frames')
    return [(request, response) for (_, request), (_, response) in zip(requests, responses)]

browser_groups = []
for pair in paired('browser'):
    if pair[0].get('op') == 'snapshot_begin':browser_groups.append([])
    browser_groups[-1].append(pair)
oracles = decode_capture(serial)['oracles']
require(len(browser_groups) == 3 and len(oracles) == 6, 'Browser oracle missing')
for index, group in enumerate(browser_groups):check_browser(group, oracles[2*index:2*index+2], sources[index]['browser'], report)
notes_groups = []
for pair in paired('notes'):
    if pair[0].get('op') == 'snapshot':notes_groups.append([])
    notes_groups[-1].append(pair)
require(len(notes_groups) == 3 and len(notes_groups[0]) == 1 and notes_groups[0][0][1].get('capped') is True, 'capped response missing')
original = (out / 'synthetic-input.txt').read_text()
for index in (1, 2):
    _, _, text, revision, failure = notes_segment(notes_groups[index], report['processes']['notes'])
    require(failure is None and text == original and revision == sources[index]['notes']['revision'], 'recovered Notes transaction mismatch')
    digest = hashlib.sha256(text.encode()).hexdigest().encode()
    require(re.search(rb'SSG_TEST_OWNER_DOCUMENT units=' + str(len(text.encode('utf-16-le')) // 2).encode() + rb' sha256=' + digest + rb'\b', serial), 'owner digest mismatch')
require(len(report['events']) == 2 and all(event['key'] == 'pgdn' for event in report['events']), 'two QMP inputs missing')
for entry in report['events']:
    ready=serial.find(('P3C_CYCLE_READY cycle=%d ' % entry['cycle']).encode())
    following=serial.find(('P3C_CYCLE_READY cycle=%d ' % (entry['cycle']+1)).encode(),ready+1)
    require(0<=ready<=entry['serial_offset']<following, 'input outside its observation interval')
    require(any(e.get('command')=='input-send-event' and entry['serial_offset']<=e.get('serial_offset',-1)<following and
        any(item.get('type')=='key' and item.get('data',{}).get('down') is True and item.get('data',{}).get('key',{}).get('data')=='pgdn'
            for item in (e.get('arguments') or {}).get('events',[])) for e in report.get('qmp_events',[])), 'QMP input not recorded')
result = {'status': 'PARTIAL_RECOVERY_VERIFIED', 'scope': 'the initial source observation was incomplete; later full observations were independently verified',
          'first_snapshot_capped': True, 'query_duration_ns': notes_groups[0][0][1].get('queryDurationNs'),
          'notes_events': [event['event_type'] for event in events[1::2]], 'resources_restored': True,
          'source_exits': report['source_exits']}
(out / 'partial-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
