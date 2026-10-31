#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check framed-event continuity and rejection of incomplete records."""
import base64
import json
from ssg_watch_events import decode_event_records

payload = json.dumps({'slot': 'example', 'sequence': '1', 'summary': {'value': 'x' * 400}}, separators=(',', ':')).encode()
encoded = base64.b64encode(payload)
records = [b'P3C_EVENT_BEGIN 1 %d %d' % (len(payload), len(encoded))]
records += [b'P3C_EVENT_PART 1 %d %s' % (offset, encoded[offset:offset+96]) for offset in range(0, len(encoded), 96)]
records += [b'P3C_EVENT_END 1']
assert all(len(line) + 2 <= 256 for line in records)
stop = b'P3C_WATCH_STOP reason=CYCLE_LIMIT cycles=1 events=1 dropped=0 resync=AS_NEEDED aggregate=OBSERVED_COMPLETE elapsed_ns=1'
noisy = b'P3C_WATCH_STARTED synthetic\nother process partial output\n' + b'\nEDITOR_SAMPLE pages=1\n'.join(records) + b'\n' + stop + b'\n'
result = decode_event_records(noisy)
assert len(result) == 1 and result[0]['payload'] == payload and result[0]['data']['sequence'] == '1'
two_streams = decode_event_records(noisy + noisy)
assert [item['stream'] for item in two_streams] == [1, 2] and [item['sequence'] for item in two_streams] == [1, 1]
for broken in (records[:-1], records[:2] + records[3:], records + records,
               [records[0], records[2], *records[3:]], [b'P3C_EVENT_BEGIN 1 9000 12000'], []):
    try:
        decode_event_records(b'P3C_WATCH_STARTED synthetic\n' + b'\n'.join(broken) + b'\n' + stop + b'\n')
    except (ValueError, json.JSONDecodeError):
        continue
    raise AssertionError('malformed or incomplete stream was accepted')
print('P3C_EVENT_FRAME_TEST PASS: noise, missing data, ordering, duplicates and bounds')
