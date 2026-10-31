#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check ordinary watch output without claiming an independent IPC oracle."""
import json
from pathlib import Path
import re
import sys
from ssg_watch_events import decode_event_records

out = Path(sys.argv[1])
report = json.loads((out / 'report.json').read_text())
serial = (out / 'serial.log').read_bytes()
event_records = decode_event_records(serial)
assert len({record['stream'] for record in event_records}) == 1
events = [record['data'] for record in event_records]
assert report['ordinary'] and report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION'
assert report['resources_restored'] and report['supervisor_exit'] == {'kind': 'exited', 'code': 0}
assert len(events) == 6 and b'P3B_FRAME_' not in serial and b'SSG_ORACLE_' not in serial
assert b'globalAtomicSnapshot=NOT_IMPLEMENTED' in serial
for index, event in enumerate(events):
    assert event['slot'] == ('browser', 'notes')[index % 2] and event['sequence'] == str(index // 2 + 1)
    assert event['event_type'] == ('SOURCE_UNKNOWN' if index < 2 else 'SOURCE_UNCHANGED')
    assert event['baseline_state'] == 'CURRENT_OBSERVATION'
    if '--require-structured' in sys.argv[2:]:
        assert isinstance(event['identity_namespace'], dict)
    assert (out / 'synthetic-input.txt').read_text()[:64] not in json.dumps(event)
result = {'status': 'OBSERVED', 'scope': 'ordinary binaries, no raw IPC oracle', 'cycles': 3,
          'events': len(events), 'resources_restored': True, 'global_atomic_snapshot': 'NOT_IMPLEMENTED'}
(out / 'ordinary-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
