#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify bounded retry using a real Notes process with synthetic cap faults."""
import hashlib
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
case = report['case']
require(case in ('cap-retry', 'cap-persistent') and report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'guest did not complete')
require(report['resources_restored'] and report['supervisor_exit'] == {'kind': 'exited', 'code': 0}, 'unclean shutdown')
serial = (out / 'serial.log').read_bytes();data = frames(serial)
samples = [data[('aggregate', 'BASELINE', i)] for i in (1, 2, 3)]
sources = [{source['slot']: source for source in sample['sources']} for sample in samples]
check_wiring(serial, report, sources[0]);verify_browser_receipt(out / 'browser.receipt.json', report)
for sample, pair in zip(samples, sources):
    require(sample['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'atomic snapshot claimed')
    for source in pair.values():check_source_metadata(source)
event_records = decode_event_records(serial)
require(len({record['stream'] for record in event_records}) == 1, 'unexpected watch stream count')
events = [record['data'] for record in event_records]
require(len(events) == 6 and all(isinstance(event['identity_namespace'], dict) for event in events), 'event metadata missing')
require([event['event_type'] for event in events[::2]] == ['SOURCE_UNKNOWN', 'SOURCE_UNCHANGED', 'SOURCE_UNCHANGED'], 'Browser changed')

def grouped(slot, begin):
    requests = sorted((seq, value) for (s, direction, seq), value in data.items() if s == slot and direction == 'REQ')
    responses = sorted((seq, value) for (s, direction, seq), value in data.items() if s == slot and direction == 'RESP')
    require([seq for seq, _ in requests] == [seq for seq, _ in responses], 'source frames not paired')
    result = []
    for (_, request), (_, response) in zip(requests, responses):
        if request.get('op') == begin:result.append([])
        require(result, 'missing snapshot')
        result[-1].append((request, response))
    return result

browser_groups = grouped('browser', 'snapshot_begin');oracles = decode_capture(serial)['oracles']
require(len(browser_groups) == 3 and len(oracles) == 6, 'Browser oracle missing')
for index, group in enumerate(browser_groups):check_browser(group, oracles[2*index:2*index+2], sources[index]['browser'], report)
notes_groups = grouped('notes', 'snapshot');original = (out / 'synthetic-input.txt').read_text()
note_events = events[1::2]
if case == 'cap-retry':
    ready_groups = [];pending = 0
    for group in notes_groups:
        if group[0][1].get('capped') is True:
            require(len(group) == 1, 'capped snapshot had range requests');pending += 1
        else:
            ready_groups.append((pending, group));pending = 0
    require(pending == 0 and len(ready_groups) == 3 and ready_groups[0][0] >= 1, 'initial capped fault missing')
    require(serial.count(b'P3C_TEST_CAPPED injected=1') == 1 and serial.count(b'P3C_NOTES_RETRY reason=CAPPED') == sum(count for count, _ in ready_groups), 'retry count')
    require([event['retry_count'] for event in note_events] == [count for count, _ in ready_groups] and
            all(count <= 2 for count, _ in ready_groups), 'event retry count')
    require([event['event_type'] for event in note_events] == ['SOURCE_UNKNOWN', 'SOURCE_UNCHANGED', 'SOURCE_UNCHANGED'], 'recovered events')
    for index, (_, group) in enumerate(ready_groups):
        _, _, text, revision, failure = notes_segment(group, report['processes']['notes'])
        require(failure is None and text == original and revision == sources[index]['notes']['revision'], 'retried transaction mismatch')
        require(sources[index]['notes']['document']['text'] == text and sources[index]['notes']['status'] == 'OBSERVED_COMPLETE', 'retried baseline missing')
        digest = hashlib.sha256(text.encode()).hexdigest().encode()
        require(re.search(rb'SSG_TEST_OWNER_DOCUMENT units=' + str(len(text.encode('utf-16-le')) // 2).encode() + rb' sha256=' + digest + rb'\b', serial), 'owner digest mismatch')
else:
    require(len(notes_groups) == 9 and all(len(group) == 1 and group[0][1].get('capped') is True for group in notes_groups), 'persistent cap missing')
    require(serial.count(b'P3C_TEST_CAPPED injected=1') == 9 and serial.count(b'P3C_NOTES_RETRY reason=CAPPED') == 6, 'retry bound')
    require([event['retry_count'] for event in note_events] == [2, 2, 2], 'event retry bound')
    require(all(event['event_type'] == 'SOURCE_UNKNOWN' and event['failure_reason'] == 'INVALID_SNAPSHOT' for event in note_events), 'persistent cap claimed success')
    require(all(pair['notes']['status'] == 'UNKNOWN' and 'document' not in pair['notes'] for pair in sources), 'partial document published')
    require(all(sample['status'] == 'AGGREGATE_PARTIAL' for sample in samples), 'partial aggregate missing')
require(all(original[:64] not in json.dumps(event, ensure_ascii=False) for event in events), 'event published document text')
noise_inside = 0;inside = False
for line in serial.splitlines():
    if line.startswith(b'P3C_EVENT_BEGIN '):inside = True
    elif line.startswith(b'P3C_EVENT_END '):inside = False
    elif inside and line.startswith(b'P3C_TEST_NOISE '):noise_inside += 1
if '--require-noise' in sys.argv[2:]:
    require(serial.count(b'P3C_TEST_NOISE ') >= 20 and noise_inside > 0, 'concurrent console noise did not interleave with event records')
result = {'status': 'PASSED_SCOPED', 'case': case, 'scope': 'synthetic fault injected into a real Notes provider; no real documents',
          'capped_snapshots': sum(group[0][1].get('capped') is True for group in notes_groups),
          'event_retry_counts': [event['retry_count'] for event in note_events], 'interleaved_noise_records': noise_inside, 'resources_restored': True,
          'source_exits': report['source_exits']}
(out / 'capped-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
