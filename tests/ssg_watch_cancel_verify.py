#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check cooperative stop while a Notes transaction is actually stalled."""
import json
from pathlib import Path
import re
import sys
from ssg_watch_events import decode_event_records

out = Path(sys.argv[1])
report = json.loads((out / 'report.json').read_text())
serial = (out / 'serial.log').read_bytes()
assert report['case'] == 'cancel-inflight' and report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
assert report['resources_restored'] and report['supervisor_exit'] == {'kind': 'exited', 'code': 0}
fault = serial.find(b'SSG_TEST_PROVIDER_FAULT kind=CANCEL_STALL')
signal = serial.find(b'P3C_TEST_INFLIGHT_CONTROL sent=1')
discard = serial.find(b'P3B_NOTES_DISCARD reason=CANCELLED')
stop = serial.find(b'P3C_WATCH_STOP reason=EXPLICIT_STOP cycles=1 events=2 dropped=0')
assert 0 <= fault < signal < discard < stop
assert re.search(rb'P3C_WATCH_STOP reason=EXPLICIT_STOP cycles=1 events=2 dropped=0 resync=AS_NEEDED aggregate=PARTIAL', serial)
match = re.search(rb'P3B_NOTES_DISCARD reason=CANCELLED units=(\d+)', serial)
assert match and int(match[1]) > 0
event_records = decode_event_records(serial)
assert len({record['stream'] for record in event_records}) == 1
events = [record['data'] for record in event_records]
assert len(events) == 2 and [e['slot'] for e in events] == ['browser', 'notes']
assert b'P3C_EVENT_BEGIN ' not in serial[signal:]
assert all('reaped=1 cancelled=0 outcome=1 code=0' in value for value in report['source_exits'])
result = {'status': 'PASSED_SCOPED', 'scope': 'cooperative stop over a test pipe during a real stalled Notes range transaction',
          'staged_utf16_units_discarded': int(match[1]), 'events_before_stop': len(events),
          'resources_restored': True, 'source_exits': report['source_exits']}
(out / 'cancel-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
