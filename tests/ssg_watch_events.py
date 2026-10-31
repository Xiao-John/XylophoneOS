#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Decode bounded P3C event records, tolerating unrelated console lines."""
import base64
import json
import re

BEGIN = re.compile(rb'P3C_EVENT_BEGIN (\d+) (\d+) (\d+)')
PART = re.compile(rb'P3C_EVENT_PART (\d+) (\d+) ([A-Za-z0-9+/=]+)')
END = re.compile(rb'P3C_EVENT_END (\d+)')
STOP = re.compile(rb'P3C_WATCH_STOP reason=\S+ cycles=\d+ events=(\d+) dropped=(\S+) resync=(\S+) aggregate=\S+ elapsed_ns=\d+')


def unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate event key')
        result[key] = value
    return result


def decode_event_records(serial, require_stop=True):
    pending = {}
    result = []
    seen = set()
    stream = 0
    expected_sequence = 1
    stopped = False
    for line in serial.splitlines():
        if line.startswith(b'P3C_WATCH_STARTED '):
            if pending:
                raise ValueError('new watch started with an incomplete event')
            if require_stop and stream and not stopped:
                raise ValueError('watch ended without a stop record')
            stream += 1;seen.clear();expected_sequence = 1;stopped = False
            continue
        stop = STOP.fullmatch(line)
        if stop:
            if not stream or stopped or pending or int(stop[1]) != expected_sequence-1 or stop[2] != b'0' or stop[3] == b'RESET_REQUIRED':
                raise ValueError('incomplete or discontinuous stopped stream')
            stopped = True
            continue
        begin, part, end = BEGIN.fullmatch(line), PART.fullmatch(line), END.fullmatch(line)
        if begin:
            seq, length, encoded_length = map(int, begin.groups())
            if stream == 0 or stopped or seq in seen or seq < 1 or not 0 < length <= 8192 or encoded_length != 4 * ((length + 2) // 3):
                raise ValueError('invalid or duplicate event begin')
            seen.add(seq);pending[seq] = [length, encoded_length, bytearray()]
        elif part:
            seq, offset, chunk = part.groups();seq = int(seq);offset = int(offset)
            if seq not in pending or offset != len(pending[seq][2]) or len(chunk) > 96:
                raise ValueError('orphan or noncontiguous event part')
            pending[seq][2].extend(chunk)
            if len(pending[seq][2]) > pending[seq][1]:
                raise ValueError('oversized event')
        elif end:
            seq = int(end[1])
            if seq not in pending:
                raise ValueError('orphan event end')
            length, encoded_length, encoded = pending.pop(seq)
            if len(encoded) != encoded_length:
                raise ValueError('incomplete event encoding')
            payload = base64.b64decode(encoded, validate=True)
            if len(payload) != length:
                raise ValueError('event length mismatch')
            value = json.loads(payload, object_pairs_hook=unique_pairs)
            if not isinstance(value, dict):
                raise ValueError('event is not an object')
            if seq != expected_sequence:
                raise ValueError('unordered event stream')
            expected_sequence += 1
            result.append({'stream': stream, 'sequence': seq, 'payload': payload, 'data': value})
        elif line.startswith(b'P3C_EVENT_'):
            raise ValueError('malformed event record')
    if pending or (require_stop and stream and not stopped):
        raise ValueError('incomplete or unordered event stream')
    return result
