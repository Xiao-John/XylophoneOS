#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independently rebuild and compare P4A sender/Subscriber frames from QEMU logs."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import struct

frame_header_size = 28
max_frame_size = 4096
event_fields = {
    'slot', 'identity_namespace', 'source_instance', 'source_epoch',
    'source_revision_before', 'source_revision_after', 'sequence',
    'observation_start', 'observation_end', 'observation_scope',
    'presentation_state', 'capability_set', 'event_type', 'retry_count',
    'completeness', 'freshness', 'failure_reason', 'summary', 'baseline_state',
}


def unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def payload_checksum(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def decode_frames(lines, direction):
    prefix = 'P4A_' + direction
    begin_re = re.compile(r'^' + prefix + r'_BEGIN stream=(\d+) bytes=(\d+) encoded=(\d+)$')
    part_re = re.compile(r'^' + prefix + r'_PART stream=(\d+) offset=(\d+) data=([A-Za-z0-9+/=]+)$')
    end_re = re.compile(r'^' + prefix + r'_END stream=(\d+)$')
    pending = {}
    result = {}
    for raw_line in lines:
        line = raw_line.rstrip('\r')
        match = begin_re.fullmatch(line)
        if match:
            sequence, length, encoded_length = map(int, match.groups())
            if sequence in pending or sequence in result or not 0 < length <= max_frame_size:
                raise ValueError(f'{direction}: duplicate or invalid begin {sequence}')
            if encoded_length != 4 * ((length + 2) // 3):
                raise ValueError(f'{direction}: bad encoded length {sequence}')
            pending[sequence] = [length, encoded_length, bytearray()]
            continue
        match = part_re.fullmatch(line)
        if match:
            sequence, offset = int(match.group(1)), int(match.group(2))
            if sequence not in pending or offset != len(pending[sequence][2]):
                raise ValueError(f'{direction}: missing or repeated chunk {sequence}')
            chunk = match.group(3).encode('ascii')
            pending[sequence][2].extend(chunk)
            if len(pending[sequence][2]) > pending[sequence][1]:
                raise ValueError(f'{direction}: oversized encoding {sequence}')
            continue
        match = end_re.fullmatch(line)
        if match:
            sequence = int(match.group(1))
            if sequence not in pending:
                raise ValueError(f'{direction}: orphan end {sequence}')
            length, encoded_length, encoded = pending.pop(sequence)
            if len(encoded) != encoded_length:
                raise ValueError(f'{direction}: truncated encoding {sequence}')
            frame = base64.b64decode(encoded, validate=True)
            if len(frame) != length:
                raise ValueError(f'{direction}: frame length mismatch {sequence}')
            result[sequence] = frame
    if pending:
        raise ValueError(f'{direction}: unfinished captures {sorted(pending)}')
    return result


def expected_consumer_state(event):
    event_type = event['event_type']
    failure = event['failure_reason']
    current = event['baseline_state'] == 'CURRENT_OBSERVATION'
    if event_type == 'SOURCE_CHANGED':
        return 'CHANGED'
    if event_type == 'SOURCE_UNCHANGED':
        return 'UNCHANGED'
    if event_type == 'SOURCE_REPLACED' and current:
        return 'REPLACED'
    if event_type == 'SOURCE_UNAVAILABLE':
        return 'UNAVAILABLE'
    if event_type == 'SOURCE_INVALIDATED' or event_type == 'RESET_REQUIRED':
        return 'RESET_REQUIRED'
    if event_type == 'PERMISSION_CHANGED' and current:
        return 'RESET_REQUIRED'
    if failure == 'DENIED':
        return 'DENIED'
    if failure == 'PROTECTED':
        return 'PROTECTED'
    if current:
        return 'OBSERVED'
    return 'UNKNOWN'


def verify(directory):
    directory = Path(directory)
    serial = (directory / 'serial.log').read_bytes().decode('latin1').splitlines()
    report = json.loads((directory / 'report.json').read_text())
    if report.get('status') != 'PASSED_SCOPED':
        raise ValueError('guest scenario did not pass')
    scenario = report.get('scenario')
    tx_frames = decode_frames(serial, 'TX')
    rx_frames = decode_frames(serial, 'RX')
    if not tx_frames or set(tx_frames) != set(rx_frames):
        raise ValueError('sender/receiver frame sets differ')
    sequences = sorted(tx_frames)
    if sequences != list(range(1, len(sequences) + 1)):
        raise ValueError('stream sequence has a gap or duplicate')

    source_instances = {}
    process_ids = {}
    for line in serial:
        match = re.fullmatch(r'P3B_SOURCE slot=(browser|notes) supervisor=(\d+) provider=(\d+) instance=([0-9a-f]{32}) channel=independent', line)
        if match:
            slot, supervisor, provider, instance = match.groups()
            if slot in source_instances:
                raise ValueError(f'duplicate source slot {slot}')
            source_instances[slot] = instance
            process_ids[slot] = int(provider)
        match = re.fullmatch(r'P3B_BOTH_STARTED supervisor=(\d+) browser=(\d+) notes=(\d+)', line)
        if match:
            process_ids['supervisor'] = int(match.group(1))
        match = re.fullmatch(r'P4A_SUBSCRIBER_STARTED supervisor=(\d+) subscriber=(\d+).*browser_instance=([0-9a-f]{32}) notes_instance=([0-9a-f]{32})', line)
        if match:
            process_ids['subscriber'] = int(match.group(2))
            if int(match.group(1)) != process_ids.get('supervisor'):
                raise ValueError('Subscriber parent does not match supervisor')
            if match.group(3) != source_instances.get('browser') or match.group(4) != source_instances.get('notes'):
                raise ValueError('prewired source identities differ from provider launches')
    if set(source_instances) != {'browser', 'notes'} or len(set(process_ids.values())) != 4:
        raise ValueError('four independent process roles or source slots are missing')

    receive_logs = {}
    ack_logs = set()
    rejected_ack_logs = set()
    ack_mismatch_logs = {}
    commit_logs = set()
    send_logs = {}
    for line in serial:
        match = re.fullmatch(r'P4A_SEND stream=(\d+) slot=(browser|notes) bytes=(\d+) frame_hash=([0-9a-f]{8})', line)
        if match:
            sequence = int(match.group(1))
            if sequence in send_logs:
                raise ValueError('duplicate sender summary')
            send_logs[sequence] = (match.group(2), int(match.group(3)), match.group(4))
        match = re.fullmatch(r'P4A_RECEIVE stream=(\d+) slot=(browser|notes) local=(\d+) type=([A-Z_]+) state=([A-Z_]+) revision=(\S*) bytes=(\d+) frame_hash=([0-9a-f]{8})', line)
        if match:
            sequence = int(match.group(1))
            if sequence in receive_logs:
                raise ValueError('duplicate Subscriber receive summary')
            receive_logs[sequence] = (match.group(2), int(match.group(3)), match.group(4),
                                      match.group(5), match.group(6), int(match.group(7)), match.group(8))
        match = re.fullmatch(r'P4A_ACK stream=(\d+) status=COMMITTED proof=SUBSCRIBER_IN_MEMORY_STATE_ONLY', line)
        if match:
            ack_logs.add(int(match.group(1)))
        match = re.fullmatch(r'P4A_ACK stream=(\d+) status=REJECTED proof=NOT_COMMITTED', line)
        if match:
            rejected_ack_logs.add(int(match.group(1)))
        match = re.fullmatch(r'P4A_ACK_HEADER stream=(\d+) .*ack_stream=(\d+) .*valid=1', line)
        if match:
            ack_mismatch_logs[int(match.group(1))] = int(match.group(2))
        match = re.fullmatch(r'P4A_SUBSCRIBER_COMMIT stream=(\d+) slot=(browser|notes) state=([A-Z_]+) commit=IN_MEMORY_READ_ONLY_STATE ack=PENDING', line)
        if match:
            commit_logs.add(int(match.group(1)))

    if scenario == 'corrupt-frame':
        if (set(send_logs) != set(sequences) or receive_logs or commit_logs or ack_logs or
            rejected_ack_logs != set(sequences) or sequences != [1]):
            raise ValueError('rejected frame was committed, acknowledged, or replayed')
        if not any(line == 'P4A_SUBSCRIBER_RESET_REQUIRED reason=CHECKSUM_INVALID stream=1' for line in serial):
            raise ValueError('Subscriber did not invalidate state after checksum failure')
        if not any(line.startswith('P4A_WATCH_STOP ') and 'attempted=1 acks=0 delivery=REJECTED resync=RESET_REQUIRED' in line for line in serial):
            raise ValueError('Supervisor did not stop and require resync after rejection')
    elif scenario == 'wrong-ack':
        if (sequences != [1] or set(send_logs) != set(sequences) or set(receive_logs) != set(sequences) or
            commit_logs != set(sequences) or ack_logs or ack_mismatch_logs != {1: 2}):
            raise ValueError('wrong ACK sequence was accepted or replayed')
        if not any(line.startswith('P4A_SUBSCRIBER_ACK status=SENT stream=1 ack_sequence=2') for line in serial):
            raise ValueError('Subscriber did not emit the deliberately mismatched ACK')
        if not any(line.startswith('P4A_WATCH_STOP ') and 'attempted=1 acks=0 delivery=UNKNOWN resync=RESET_REQUIRED' in line for line in serial):
            raise ValueError('wrong ACK did not produce UNKNOWN and require resync')
    elif scenario == 'duplicate-ack':
        if (sequences != [1, 2] or set(send_logs) != set(sequences) or set(receive_logs) != set(sequences) or
            commit_logs != set(sequences) or ack_logs != {1} or ack_mismatch_logs != {2: 1}):
            raise ValueError('duplicate ACK was not rejected as a sequence mismatch')
        if not any(line.startswith('P4A_SUBSCRIBER_ACK status=SENT stream=1 ack_sequence=1 duplicate=1') for line in serial):
            raise ValueError('Subscriber did not emit the duplicate ACK fault')
        if not any(line.startswith('P4A_WATCH_STOP ') and 'attempted=2 acks=1 delivery=UNKNOWN resync=RESET_REQUIRED' in line for line in serial):
            raise ValueError('duplicate ACK did not stop the stream with UNKNOWN')
    elif scenario == 'backpressure':
        if set(send_logs) != set(sequences) or set(receive_logs) != set(sequences) or commit_logs != set(sequences):
            raise ValueError('backpressure stream is missing send, receive, or commit records')
        if ack_logs or sequences != [1]:
            raise ValueError('uncertain delivery was acknowledged or more than one event was sent')
        if not any(line == 'P4A_BACKPRESSURE_PROBE result=WOULD_BLOCK frame_bytes=4096 atomic=1' for line in serial):
            raise ValueError('guest Pipe did not demonstrate full-capacity would-block')
        if not any(line.startswith('P4A_SUBSCRIBER_ACK status=UNKNOWN stream=1') for line in serial):
            raise ValueError('Subscriber did not report unknown ACK delivery')
        if not any(line.startswith('P4A_WATCH_STOP ') and 'attempted=1 acks=0 delivery=UNKNOWN resync=RESET_REQUIRED' in line for line in serial):
            raise ValueError('Supervisor did not stop and require resync after ACK timeout')
    else:
        if (set(send_logs) != set(sequences) or set(receive_logs) != set(sequences) or
            commit_logs != set(sequences) or ack_logs != set(sequences)):
            raise ValueError('sender, receive, commit, and ACK logs do not cover the same stream')

    local_sequences = {'browser': 0, 'notes': 0}
    events = []
    for sequence in sequences:
        tx = tx_frames[sequence]
        rx = rx_frames[sequence]
        if tx != rx:
            raise ValueError(f'frame bytes differ for stream {sequence}')
        if len(tx) < frame_header_size or len(tx) > max_frame_size:
            raise ValueError(f'frame size invalid for stream {sequence}')
        magic, version, declared_header_size, kind, flags, wire_sequence, payload_size, checksum, slot_id, reserved = struct.unpack(
            '<4sHHHHIIIHH', tx[:frame_header_size])
        if (magic, version, declared_header_size, kind, flags, wire_sequence, reserved) != (b'SGEV', 1, frame_header_size, 1, 0, sequence, 0):
            raise ValueError(f'frame header invalid for stream {sequence}')
        payload = tx[frame_header_size:]
        if payload_size != len(payload):
            raise ValueError(f'frame payload length invalid for stream {sequence}')
        checksum_valid = payload_checksum(payload) == checksum
        if scenario == 'corrupt-frame' and checksum_valid:
            raise ValueError('corrupt-frame case unexpectedly has a valid checksum')
        if scenario != 'corrupt-frame' and not checksum_valid:
            raise ValueError(f'frame payload checksum invalid for stream {sequence}')
        event = json.loads(payload, object_pairs_hook=unique_pairs)
        if set(event) != event_fields:
            raise ValueError(f'event fields are incomplete or include content for stream {sequence}')
        slot = event['slot']
        expected_slot_id = 1 if slot == 'browser' else 2 if slot == 'notes' else 0
        candidate_local_sequence = local_sequences[slot] + 1
        if slot_id != expected_slot_id or event['sequence'] != str(candidate_local_sequence):
            raise ValueError(f'slot or source-local sequence invalid for stream {sequence}')
        if scenario != 'corrupt-frame':
            local_sequences[slot] += 1
        namespace = event['identity_namespace']
        if namespace != {'slot': slot, 'source_instance': event['source_instance'], 'source_epoch': event['source_epoch']}:
            raise ValueError(f'identity namespace mismatch for stream {sequence}')
        if event['source_instance'] != source_instances[slot]:
            raise ValueError(f'frame instance does not match prewired {slot} provider')
        if not isinstance(event['summary'], dict) or len(json.dumps(event['summary'], separators=(',', ':'))) > 512:
            raise ValueError(f'event summary exceeds bounds for stream {sequence}')
        if any(key in event for key in ('text', 'document', 'nodes', 'dom', 'tree')):
            raise ValueError(f'event carries content rather than a bounded summary for stream {sequence}')

        sent_slot, sent_bytes, sent_hash = send_logs[sequence]
        computed_frame_hash = f'{payload_checksum(tx):08x}'
        if sent_slot != slot or sent_bytes != len(tx) or sent_hash != computed_frame_hash:
            raise ValueError(f'sender frame summary does not match raw frame {sequence}')
        if scenario == 'corrupt-frame':
            events.append({'stream_sequence': sequence, 'slot': slot, 'source_instance': event['source_instance'],
                           'source_epoch': event['source_epoch'], 'source_sequence': candidate_local_sequence,
                           'event_type': event['event_type'], 'consumer_state': 'RESET_REQUIRED',
                           'frame_bytes': len(tx), 'source_revision_before': event['source_revision_before'],
                           'source_revision_after': event['source_revision_after'],
                           'observation_scope': event['observation_scope'], 'baseline_state': event['baseline_state'],
                           'completeness': event['completeness'], 'freshness': event['freshness'],
                           'failure_reason': event['failure_reason'], 'summary': event['summary'],
                           'frame_sha256': hashlib.sha256(tx).hexdigest(), 'acknowledged': False,
                           'committed': False, 'checksum_valid': False})
            continue

        recv_slot, local_sequence, recv_type, recv_state, recv_revision, recv_bytes, recv_hash = receive_logs[sequence]
        if recv_slot != slot or recv_type != event['event_type']:
            raise ValueError(f'sender/Subscriber source or event type mismatch for stream {sequence}')
        if local_sequence != local_sequences[slot] or recv_revision != event['source_revision_after']:
            raise ValueError(f'Subscriber state does not match received event for stream {sequence}')
        if recv_state != expected_consumer_state(event):
            raise ValueError(f'Subscriber state transition mismatch for stream {sequence}')
        if recv_bytes != len(tx) or sent_hash != recv_hash:
            raise ValueError(f'frame audit hash/length mismatch for stream {sequence}')
        events.append({'stream_sequence': sequence, 'slot': slot, 'source_instance': event['source_instance'],
                       'source_epoch': event['source_epoch'], 'source_sequence': local_sequence,
                       'event_type': recv_type, 'consumer_state': recv_state, 'frame_bytes': len(tx),
                       'source_revision_before': event['source_revision_before'],
                       'source_revision_after': event['source_revision_after'],
                       'observation_scope': event['observation_scope'],
                       'baseline_state': event['baseline_state'],
                       'completeness': event['completeness'], 'freshness': event['freshness'],
                       'failure_reason': event['failure_reason'], 'summary': event['summary'],
                       'frame_sha256': hashlib.sha256(tx).hexdigest(),
                       'acknowledged': sequence in ack_logs, 'committed': sequence in commit_logs,
                       'checksum_valid': checksum_valid})

    if scenario == 'backpressure' and len(tx_frames[1]) != max_frame_size:
        raise ValueError('backpressure event did not fill the actual Pipe capacity')

    expected_local = ({'browser': 0, 'notes': 0} if scenario == 'corrupt-frame' else
                      {'browser': 1, 'notes': 0} if scenario in ('backpressure', 'wrong-ack') else
                      {'browser': 1, 'notes': 1} if scenario == 'duplicate-ack' else
                      {'browser': 1, 'notes': 1} if scenario in ('first', 'cancel-inflight') else
                      {'browser': 2, 'notes': 2} if scenario == 'stop' else
                      {'browser': 3, 'notes': 3})
    if local_sequences != expected_local:
        raise ValueError('source-local event sequence totals are unexpected')
    by_slot = {slot: [item for item in events if item['slot'] == slot] for slot in ('browser', 'notes')}
    if scenario == 'first':
        if any(item['event_type'] != 'SOURCE_UNKNOWN' or item['consumer_state'] != 'OBSERVED'
               for slot in by_slot.values() for item in slot):
            raise ValueError('initial subscription did not establish two observed baselines')
    elif scenario == 'stop':
        if any([item['event_type'] for item in by_slot[slot]] != ['SOURCE_UNKNOWN', 'SOURCE_UNCHANGED']
               for slot in ('browser', 'notes')):
            raise ValueError('bounded stop did not leave both sources at their sequential baseline')
        if not any(line.startswith('P4A_WATCH_STOP reason=EXPLICIT_STOP cycles=2 events=4 attempted=4 acks=4 delivery=ACKED') for line in serial):
            raise ValueError('explicit stop did not end after four confirmed frames')
    elif scenario == 'cancel-inflight':
        if any([item['event_type'] for item in by_slot[slot]] != ['SOURCE_UNKNOWN']
               for slot in ('browser', 'notes')):
            raise ValueError('cancellation published a partial or extra cycle')
        if not any(line.startswith('P4A_WATCH_STOP reason=EXPLICIT_STOP cycles=1 events=2 attempted=2 acks=2 delivery=ACKED') for line in serial):
            raise ValueError('in-flight cancellation did not stop at its last confirmed cycle')
    elif scenario == 'notes-edit':
        notes, browser = by_slot['notes'], by_slot['browser']
        if ([item['event_type'] for item in notes] != ['SOURCE_UNKNOWN', 'SOURCE_CHANGED', 'SOURCE_CHANGED'] or
            any(item['summary'].get('text_changed') is not True or item['summary'].get('revision_changed') is not True
                for item in notes[1:]) or notes[1]['source_revision_after'] == notes[0]['source_revision_after'] or
            notes[2]['source_revision_after'] == notes[1]['source_revision_after'] or
            any(item['event_type'] != 'SOURCE_UNCHANGED' for item in browser[1:])):
            raise ValueError('Notes edits or Browser isolation were not reflected in source summaries')
    elif scenario == 'browser-scroll':
        browser, notes = by_slot['browser'], by_slot['notes']
        if ([item['event_type'] for item in browser] != ['SOURCE_UNKNOWN', 'SOURCE_CHANGED', 'SOURCE_CHANGED'] or
            any(item['summary'].get('scroll_changes') != 1 or
                item['summary'].get('scroll_before') == item['summary'].get('scroll_after') for item in browser[1:]) or
            any(item['event_type'] != 'SOURCE_UNCHANGED' for item in notes[1:])):
            raise ValueError('Browser scroll or Notes isolation was not reflected in source summaries')
    elif scenario in ('notes-revoke', 'protect-document', 'protect-ancestor'):
        expected_state = 'DENIED' if scenario == 'notes-revoke' else 'PROTECTED'
        notes, browser = by_slot['notes'], by_slot['browser']
        if (notes[1]['event_type'] != 'PERMISSION_CHANGED' or notes[1]['failure_reason'] != expected_state or
            notes[1]['consumer_state'] != expected_state or notes[1]['baseline_state'] != 'HISTORICAL_OR_ABSENT' or
            notes[2]['failure_reason'] != expected_state or notes[2]['consumer_state'] != expected_state or
            any(item['event_type'] != 'SOURCE_UNCHANGED' for item in browser[1:])):
            raise ValueError('Notes restriction was not reflected without changing Browser state')
    elif scenario == 'browser-exit':
        if (any(item['event_type'] != 'SOURCE_UNAVAILABLE' or item['consumer_state'] != 'UNAVAILABLE'
                for item in by_slot['browser'][1:]) or
            any(item['event_type'] != 'SOURCE_UNCHANGED' for item in by_slot['notes'][1:])):
            raise ValueError('Browser exit invalidation or Notes continuation was not observed')
    elif scenario == 'notes-exit':
        if (any(item['event_type'] != 'SOURCE_UNAVAILABLE' or item['consumer_state'] != 'UNAVAILABLE'
                for item in by_slot['notes'][1:]) or
            any(item['event_type'] != 'SOURCE_UNCHANGED' for item in by_slot['browser'][1:])):
            raise ValueError('Notes exit invalidation or Browser continuation was not observed')
    if scenario in ('backpressure', 'corrupt-frame', 'wrong-ack', 'duplicate-ack'):
        expected_subscriber = {
            'backpressure': 'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=4 clean=0',
            'corrupt-frame': 'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=3 clean=0',
            'wrong-ack': 'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=0 clean=1',
            'duplicate-ack': 'P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=4 clean=0',
        }[scenario]
        if not any(line.startswith(expected_subscriber) for line in serial):
            raise ValueError('fault-case Subscriber lifecycle was not observed')
        if report.get('supervisor_exit') != {'kind': 'exited', 'code': 1}:
            raise ValueError('delivery failure was reported as successful')
        if scenario == 'backpressure' and (ack_logs or not any(line.startswith('P4A_SUBSCRIBER_ACK status=UNKNOWN stream=1') for line in serial)):
            raise ValueError('ACK timeout did not remain UNKNOWN')
        if scenario == 'corrupt-frame' and (ack_logs or rejected_ack_logs != set(sequences)):
            raise ValueError('corrupt event did not receive only a rejection')
    else:
        if not any(line.startswith('P4A_SUBSCRIBER_EXIT reaped=1 cancelled=0 outcome=1 code=0 clean=1') for line in serial):
            raise ValueError('Subscriber did not exit cleanly')
        if report.get('supervisor_exit') != {'kind': 'exited', 'code': 0}:
            raise ValueError('Supervisor did not exit cleanly after confirmed delivery')
    if not report.get('resources_restored'):
        raise ValueError('resource counters were not restored')
    source_exits = [line for line in serial if line.startswith('P3B_SOURCE_EXIT ')]
    if len(source_exits) != 2 or any('reaped=1 cancelled=0 outcome=1 code=0' not in line for line in source_exits):
        raise ValueError('Provider children did not exit cleanly')
    if not any(line.startswith('P3B_SHUTDOWN ') and 'clean=1' in line for line in serial):
        raise ValueError('Provider shutdown was not clean')

    result = {'status': 'PASSED_SCOPED', 'events': events,
              'processes': report['processes'], 'resources_restored': True,
              'semantics': 'per-source sequential observations; globalAtomicSnapshot=NOT_IMPLEMENTED'}
    (directory / 'independent_check.json').write_text(json.dumps(result, indent=2) + '\n')
    print('P4A_INDEPENDENT_AUDIT PASSED_SCOPED events=' + str(len(events)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    verify(args.run)


if __name__ == '__main__':
    main()
