#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independently check the frozen close barriers in the actual Ethernet capture.

Run in place; stdout is a derived JSON audit. This consumes no network and uses
no live-peer implementation. The guest fixture's source-bound native send and
close assertions establish admission; the capture establishes the wire state.
"""
import base64
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
MASK = 0xffffffff


def checked(data):
    padded = data + (b'\0' if len(data) % 2 else b'')
    value = sum((padded[i] << 8) | padded[i + 1] for i in range(0, len(padded), 2))
    while value > 0xffff:
        value = (value & 0xffff) + (value >> 16)
    return value == 0xffff


capture = base64.b64decode((ROOT / 'transport_window.pcap.b64').read_bytes())
assert capture[:4] == b'\xd4\xc3\xb2\xa1' and struct.unpack_from('<I', capture, 20)[0] == 1
offset, frame_number, packets = 24, 0, []
while offset < len(capture):
    _, _, captured, actual = struct.unpack_from('<IIII', capture, offset)
    offset += 16
    assert captured == actual and offset + captured <= len(capture)
    frame, offset = capture[offset:offset + captured], offset + captured
    frame_number += 1
    if frame[12:14] != b'\x08\x00':
        continue
    ip = frame[14:]
    header, total = (ip[0] & 15) * 4, int.from_bytes(ip[2:4], 'big')
    assert ip[0] >> 4 == 4 and 20 <= header <= total <= len(ip) and checked(ip[:header])
    body, protocol = ip[header:total], ip[9]
    if protocol not in (6, 17):
        continue
    pseudo = ip[12:20] + struct.pack('!BBH', 0, protocol, len(body))
    assert checked(pseudo + body)
    row = {'frame': frame_number, 'protocol': protocol, 'source': ip[12:16].hex(),
           'src_port': int.from_bytes(body[:2], 'big'), 'dst_port': int.from_bytes(body[2:4], 'big')}
    if protocol == 6:
        size = (body[12] >> 4) * 4
        assert 20 <= size <= len(body)
        row.update(sequence=int.from_bytes(body[4:8], 'big'), ack=int.from_bytes(body[8:12], 'big'),
                   flags=body[13], window=int.from_bytes(body[14:16], 'big'), data=body[size:])
    else:
        assert int.from_bytes(body[4:6], 'big') == len(body)
        row['data'] = body[8:]
    packets.append(row)

transport = json.loads((ROOT / 'transport.json').read_text())
assert transport['status'] == 'passed' and len(transport['controlled_closes']) == 4
audits = []
for flow in transport['controlled_closes']:
    port, nonce, count = flow['peer_port'], flow['nonce'].encode(), flow['close_barrier']['accepted_bytes']
    tcp = [p for p in packets if p['protocol'] == 6 and (p['src_port'] == port or p['dst_port'] == port)]
    client = [p for p in tcp if p['dst_port'] == port]
    peer = [p for p in tcp if p['src_port'] == port]
    assert all(p['source'] == '0a00020f' for p in client)
    assert all(p['source'] == '0a000202' for p in peer)
    assert all(not p['flags'] & 4 for p in tcp)
    syn = next(p for p in client if p['flags'] == 2)
    base = (syn['sequence'] + 1) & MASK
    barriers = [p for p in packets if p['protocol'] == 17 and p['dst_port'] == port + 1 and p['data'] == nonce]
    assert len(barriers) == 1
    barrier = barriers[0]['frame']
    challenges = [p for p in peer if hashlib.sha256(p['data']).hexdigest() == flow['challenge_sha256']]
    assert len(challenges) == 1 and len(challenges[0]['data']) == 32
    challenge = challenges[0]
    expected, observed = nonce * (1 + count // 32), {}
    for packet in client:
        if not packet['data']:
            continue
        start = (packet['sequence'] - base) & MASK
        end = start + len(packet['data'])
        assert end <= len(expected) and packet['data'] == expected[start:end]
        observed.update(enumerate(packet['data'], start))
    assert bytes(observed[i] for i in range(len(expected))) == expected
    assert hashlib.sha256(expected).hexdigest() == flow['request_sha256']
    fins = [p for p in client if p['flags'] & 1]
    assert fins and all((p['sequence'] + len(p['data'])) & MASK == (base + len(expected)) & MASK for p in fins)
    fin = min(p['frame'] for p in fins)
    audit = {'mode': flow['mode'], 'shell': flow['shell'], 'peer_port': port, 'challenge_frame': challenge['frame'],
             'close_barrier_frame': barrier, 'client_fin_frame': fin, 'verified_payload_bytes': count}
    if flow['mode'] == 'queued':
        assert challenge['window'] == 0 and challenge['frame'] < barrier < fin
        assert all(p['window'] == 0 for p in peer if challenge['frame'] <= p['frame'] < barrier)
        probes = [p for p in client if p['frame'] < barrier and p['data'] and
                  ((p['sequence'] - base) & MASK) + len(p['data']) > 32]
        assert all(((p['sequence'] - base) & MASK) == 32 and len(p['data']) == 1 for p in probes)
        unsent = count - int(bool(probes))
        assert flow['close_barrier']['unsent_bytes_lower_bound'] == unsent
        release = next(p['frame'] for p in peer if p['frame'] > barrier and p['window'])
        data = next(p['frame'] for p in client if p['frame'] > barrier and p['data'])
        assert release < data <= fin
        audit.update(window_release_frame=release, first_payload_after_release_frame=data,
                     probe_frames_before_barrier=len(probes), unsent_bytes_lower_bound_at_close=unsent)
    else:
        confirmation = next(p for p in peer if p['data'] == b'\xa5')
        assert confirmation['ack'] == (base + len(expected)) & MASK
        assert confirmation['frame'] < fin < barrier
        audit.update(full_payload_ack_frame=confirmation['frame'], acknowledged_before_close=count)
    audits.append(audit)
print(json.dumps({'status': 'passed', 'source_capture': 'original window_network.pcap decoded from base64',
                  'source_capture_sha256': hashlib.sha256(capture).hexdigest(),
                  'ethernet_frames': frame_number, 'flows': audits}, indent=2))
