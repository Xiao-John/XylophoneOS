#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify a rejected session is followed by new identities and fresh baselines."""
import argparse
import json
from pathlib import Path
import re


def source_instances(directory):
    serial = (directory / 'serial.log').read_bytes().decode('latin1').splitlines()
    result = {}
    for line in serial:
        match = re.fullmatch(r'P3B_SOURCE slot=(browser|notes) supervisor=\d+ provider=\d+ instance=([0-9a-f]{32}) channel=independent', line)
        if match:
            if match.group(1) in result:
                raise ValueError('duplicate source instance in session')
            result[match.group(1)] = match.group(2)
    if set(result) != {'browser', 'notes'}:
        raise ValueError('both prewired source identities are required')
    return result


def verify(rejected_run, baseline_run):
    rejected_run, baseline_run = Path(rejected_run), Path(baseline_run)
    rejected_report = json.loads((rejected_run / 'report.json').read_text())
    baseline_report = json.loads((baseline_run / 'report.json').read_text())
    rejected_check = json.loads((rejected_run / 'independent_check.json').read_text())
    baseline_check = json.loads((baseline_run / 'independent_check.json').read_text())
    if rejected_check.get('status') != 'PASSED_SCOPED' or baseline_check.get('status') != 'PASSED_SCOPED':
        raise ValueError('both independent frame audits must pass')
    failure_mode = rejected_report.get('scenario')
    if failure_mode not in ('corrupt-frame', 'backpressure') or baseline_report.get('scenario') != 'first':
        raise ValueError('runs do not match reject-then-resync scenarios')
    rejected_events = rejected_check.get('events', [])
    baseline_events = baseline_check.get('events', [])
    if len(rejected_events) != 1 or rejected_events[0]['acknowledged']:
        raise ValueError('failed delivery was acknowledged or replayed')
    if failure_mode == 'corrupt-frame' and (rejected_events[0]['committed'] or rejected_events[0]['checksum_valid']):
        raise ValueError('corrupt event was committed or had a valid checksum')
    if failure_mode == 'backpressure' and (not rejected_events[0]['committed'] or not rejected_events[0]['checksum_valid']):
        raise ValueError('ACK-timeout event did not leave committed-but-unknown state')
    if len(baseline_events) != 2 or [item['stream_sequence'] for item in baseline_events] != [1, 2]:
        raise ValueError('fresh session did not begin with two events from sequence one')
    if any(item['event_type'] != 'SOURCE_UNKNOWN' or item['baseline_state'] != 'CURRENT_OBSERVATION' or
           item['source_sequence'] != 1 or not item['acknowledged'] for item in baseline_events):
        raise ValueError('fresh session did not establish and acknowledge both new baselines')
    previous = source_instances(rejected_run)
    current = source_instances(baseline_run)
    if any(previous[slot] == current[slot] for slot in ('browser', 'notes')):
        raise ValueError('fresh session reused a previous source instance')
    serial = (rejected_run / 'serial.log').read_bytes()
    expected_delivery = b'delivery=REJECTED resync=RESET_REQUIRED' if failure_mode == 'corrupt-frame' else b'delivery=UNKNOWN resync=RESET_REQUIRED'
    if serial.count(b'P4A_SEND stream=') != 1 or expected_delivery not in serial:
        raise ValueError('rejected event was replayed or failure did not require resync')
    result = {
        'status': 'PASSED_SCOPED',
        'failed_session': {'scenario': failure_mode, 'event_count': 1,
                           'delivery': 'REJECTED' if failure_mode == 'corrupt-frame' else 'UNKNOWN',
                           'resync': 'RESET_REQUIRED',
                             'source_instances': previous},
        'new_session': {'event_count': 2, 'source_instances': current,
                        'initial_baselines_acknowledged': True},
        'replay': 'NONE',
        'semantics': 'a new session obtains a fresh baseline; no transparent replay',
    }
    result_path = baseline_run / 'resync-independent-check.json'
    result_path.write_text(json.dumps(result, indent=2) + '\n')
    print('P4A_RESYNC_INDEPENDENT_AUDIT PASSED_SCOPED')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rejected_run', type=Path)
    parser.add_argument('baseline_run', type=Path)
    args = parser.parse_args()
    verify(args.rejected_run, args.baseline_run)


if __name__ == '__main__':
    main()
