#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host reference checks for bounded P4A framing and continuity rules."""
import json
import struct

header_format = struct.Struct('<4sHHHHIIIHH')
frame_header_size = header_format.size
pipe_size = 4096
max_payload = pipe_size - frame_header_size
event_magic = b'SGEV'
protocol_version = 1
event_kind = 1
ack_kind = 2
ack_committed = 1
ack_rejected = 2
event_fields = {
    'slot', 'identity_namespace', 'source_instance', 'source_epoch',
    'source_revision_before', 'source_revision_after', 'sequence',
    'observation_start', 'observation_end', 'observation_scope',
    'presentation_state', 'capability_set', 'event_type', 'retry_count',
    'completeness', 'freshness', 'failure_reason', 'summary', 'baseline_state',
}
checks = 0


class protocol_error(ValueError):
    pass


def check(condition, name):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(name)


def checksum(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def encode_frame(kind, sequence, slot, payload, *, version=protocol_version, flags=0, reserved=0, magic=None):
    if magic is None:
        magic = event_magic if kind == event_kind else b'SGAK'
    return header_format.pack(magic, version, frame_header_size, kind, flags, sequence, len(payload),
                       checksum(payload), slot, reserved) + payload


def decode_header(frame, expected_kind):
    if len(frame) < frame_header_size:
        raise protocol_error('TRUNCATED_HEADER')
    magic, version, declared_header_size, kind, flags, sequence, payload_length, digest, slot, reserved = header_format.unpack(frame[:frame_header_size])
    expected_magic = event_magic if expected_kind == event_kind else b'SGAK'
    if magic != expected_magic or version != protocol_version or declared_header_size != frame_header_size or kind != expected_kind:
        raise protocol_error('HEADER_ID')
    if flags or reserved or sequence == 0:
        raise protocol_error('HEADER_FLAGS_OR_SEQUENCE')
    if not 0 < payload_length <= max_payload:
        raise protocol_error('LENGTH_LIMIT')
    if len(frame) != frame_header_size + payload_length:
        raise protocol_error('TRUNCATED_OR_EXTRA_PAYLOAD')
    payload = frame[frame_header_size:]
    if checksum(payload) != digest:
        raise protocol_error('CHECKSUM')
    return sequence, slot, payload


def event_payload(slot, instance, epoch, local_sequence, *, event_type='SOURCE_UNKNOWN',
                  before='', after='1', baseline='CURRENT_OBSERVATION', failure='', summary=None):
    if summary is None:
        summary = {}
    identity = {'slot': slot, 'source_instance': instance, 'source_epoch': epoch}
    return json.dumps({
        'slot': slot, 'identity_namespace': identity,
        'source_instance': instance, 'source_epoch': epoch,
        'source_revision_before': before, 'source_revision_after': after,
        'sequence': str(local_sequence), 'observation_start': '10', 'observation_end': '11',
        'observation_scope': 'synthetic-bounded', 'presentation_state': 'hidden-test',
        'capability_set': {'structure': 'SUPPORTED'}, 'event_type': event_type,
        'retry_count': 0, 'completeness': 'SCOPED', 'freshness': 'OBSERVED_NOW',
        'failure_reason': failure, 'summary': summary, 'baseline_state': baseline,
    }, separators=(',', ':')).encode()


def decode_event(frame, expected_sequence, expected_slot=None):
    sequence, slot_id, payload = decode_header(frame, event_kind)
    if sequence != expected_sequence:
        raise protocol_error('STREAM_SEQUENCE')
    if slot_id not in (1, 2):
        raise protocol_error('SOURCE_SLOT')
    if expected_slot is not None and slot_id != expected_slot:
        raise protocol_error('SOURCE_SLOT_MISMATCH')
    event = json.loads(payload, object_pairs_hook=lambda pairs: unique_pairs(pairs))
    if set(event) != event_fields:
        raise protocol_error('FIELD_SET')
    if event['slot'] != ('browser' if slot_id == 1 else 'notes'):
        raise protocol_error('JSON_SLOT_MISMATCH')
    namespace = event['identity_namespace']
    if namespace != {'slot': event['slot'], 'source_instance': event['source_instance'],
                     'source_epoch': event['source_epoch']}:
        raise protocol_error('IDENTITY_NAMESPACE')
    return event


def validate_instance(event, expected_slot, expected_instance):
    if event.get('slot') != expected_slot or event.get('source_instance') != expected_instance:
        raise protocol_error('PREWIRED_INSTANCE_MISMATCH')


def validate_transition(previous, event):
    sequence = int(event['sequence'])
    if previous is None:
        if sequence != 1 or event['event_type'] != 'SOURCE_UNKNOWN':
            raise protocol_error('INITIAL_BASELINE_REQUIRED')
        return
    if sequence != int(previous['sequence']) + 1:
        raise protocol_error('SOURCE_SEQUENCE')
    if previous['source_epoch'] != event['source_epoch'] and event['event_type'] not in (
            'SOURCE_REPLACED', 'RESET_REQUIRED', 'SOURCE_UNKNOWN', 'SOURCE_UNAVAILABLE',
            'SOURCE_INVALIDATED', 'PERMISSION_CHANGED'):
        raise protocol_error('EPOCH_REPLACEMENT_REQUIRED')
    if event['event_type'] in ('SOURCE_CHANGED', 'SOURCE_UNCHANGED'):
        if previous['baseline_state'] != 'CURRENT_OBSERVATION' or event['source_revision_before'] != previous['source_revision_after']:
            raise protocol_error('REVISION_CONTINUITY')


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise protocol_error('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def must_reject(call, name):
    try:
        call()
    except (protocol_error, ValueError, json.JSONDecodeError):
        check(True, name)
        return
    check(False, name)


def run():
    browser = event_payload('browser', 'b' * 32, 'epoch-b1', 1)
    notes = event_payload('notes', 'n' * 32, 'epoch-n1', 1)
    browser_frame = encode_frame(event_kind, 1, 1, browser)
    notes_frame = encode_frame(event_kind, 2, 2, notes)
    check(decode_event(browser_frame, 1, 1)['slot'] == 'browser', 'valid_browser_event')
    check(decode_event(notes_frame, 2, 2)['slot'] == 'notes', 'valid_notes_event')
    check(len(browser_frame) <= pipe_size and len(notes_frame) <= pipe_size, 'pipe_frame_limit')

    must_reject(lambda: decode_header(encode_frame(event_kind, 1, 1, browser, magic=b'BAD!'), event_kind), 'bad_magic')
    must_reject(lambda: decode_header(encode_frame(event_kind, 1, 1, browser, version=2), event_kind), 'unknown_version')
    must_reject(lambda: decode_header(encode_frame(event_kind, 1, 1, browser, flags=1), event_kind), 'unknown_flags')
    must_reject(lambda: decode_header(encode_frame(event_kind, 1, 1, browser, reserved=1), event_kind), 'reserved_nonzero')
    must_reject(lambda: decode_header(encode_frame(event_kind, 0, 1, browser), event_kind), 'zero_sequence')
    must_reject(lambda: decode_header(browser_frame[:frame_header_size - 1], event_kind), 'truncated_header')
    must_reject(lambda: decode_header(browser_frame[:-1], event_kind), 'truncated_payload')
    must_reject(lambda: decode_header(browser_frame + b'x', event_kind), 'extra_payload')
    must_reject(lambda: decode_header(browser_frame[:16] + struct.pack('<I', max_payload + 1) + browser_frame[20:], event_kind), 'oversized_length')
    damaged = bytearray(browser_frame);damaged[-1] ^= 1
    must_reject(lambda: decode_header(bytes(damaged), event_kind), 'checksum_damage')
    bad_slot = encode_frame(event_kind, 1, 3, browser)
    must_reject(lambda: decode_event(bad_slot, 1), 'source_slot_invalid')
    must_reject(lambda: decode_event(notes_frame, 1, 1), 'source_slot_mismatch')

    duplicate_json = b'{"slot":"browser","slot":"notes"}'
    duplicate_event = encode_frame(event_kind, 1, 1, duplicate_json)
    must_reject(lambda: decode_event(duplicate_event, 1), 'duplicate_json_key')
    content_event = json.loads(browser.decode())
    content_event['text'] = 'must not cross the Observe summary boundary'
    content_frame = encode_frame(event_kind, 1, 1, json.dumps(content_event, separators=(',', ':')).encode())
    must_reject(lambda: decode_event(content_frame, 1), 'content_field_rejected')

    ack_payload = struct.pack('<I', ack_committed)
    ack = encode_frame(ack_kind, 1, 0, ack_payload)
    check(decode_header(ack, ack_kind)[0] == 1, 'valid_ack')
    must_reject(lambda: decode_header(ack, event_kind), 'ack_event_type_confusion')
    wrong_ack = encode_frame(ack_kind, 2, 0, ack_payload)
    check(decode_header(wrong_ack, ack_kind)[0] != 1, 'wrong_ack_sequence_detected')
    two_acks = [decode_header(ack, ack_kind)[0], decode_header(ack, ack_kind)[0]]
    check(two_acks[0] == two_acks[1], 'duplicate_ack_sequence_detected')
    nack = encode_frame(ack_kind, 1, 0, struct.pack('<I', ack_rejected))
    check(struct.unpack('<I', decode_header(nack, ack_kind)[2])[0] == ack_rejected, 'rejected_ack_status')

    expected_stream = 1
    first = decode_event(browser_frame, expected_stream, 1)
    check(first['source_instance'] == 'b' * 32, 'prewired_instance_match')
    expected_stream += 1
    must_reject(lambda: decode_event(browser_frame, expected_stream, 1), 'duplicate_stream_sequence')
    must_reject(lambda: decode_event(encode_frame(event_kind, 3, 1, browser), expected_stream, 1), 'stream_sequence_gap')
    first_event = json.loads(browser)
    wrong_instance = json.loads(event_payload('browser', 'x' * 32, 'epoch-b1', 2,
                                              event_type='SOURCE_CHANGED', before='1', after='2'))
    must_reject(lambda: validate_instance(wrong_instance, 'browser', 'b' * 32), 'prewired_instance_change_rejected')
    wrong_epoch = json.loads(event_payload('browser', 'b' * 32, 'epoch-b2', 2,
                                          event_type='SOURCE_UNCHANGED', before='1', after='1'))
    must_reject(lambda: validate_transition(first_event, wrong_epoch), 'epoch_change_without_reset_rejected')
    replacement = json.loads(event_payload('browser', 'b' * 32, 'epoch-b2', 2,
                                          event_type='SOURCE_REPLACED', before='1', after='2'))
    validate_transition(first_event, replacement)
    check(replacement['event_type'] == 'SOURCE_REPLACED', 'replacement_accepts_new_epoch_baseline')
    changed_revision = json.loads(event_payload('browser', 'b' * 32, 'epoch-b1', 2,
                                                event_type='SOURCE_CHANGED', before='stale', after='2'))
    must_reject(lambda: validate_transition(first_event, changed_revision), 'revision_mismatch_requires_reset')
    check(checks == 29, f'expected 29 checks before final tally, saw {checks}')
    print(f'P4A_HOST_REFERENCE_TEST PASSED checks={checks}')


if __name__ == '__main__':
    run()
