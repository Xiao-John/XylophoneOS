#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independently check captured Notes transaction frames and owner digests."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(value):
    return hashlib.sha256(value).hexdigest()


def units(value):
    return len(value.encode('utf-16-le')) // 2


def utf16_slice(value, start, end):
    return value.encode('utf-16-le')[start * 2:end * 2].decode('utf-16-le')


def verify(directory):
    report = json.loads((directory / 'report.json').read_text())
    assert report['status'] == 'GUEST_RUN_CAPTURED'
    case = report['case']
    # Construct the reference independently from the fixed fixture definition.
    source = 'A' * 511 + '\U0001f600\n' + ''.join(
        f'{i:04d} Alpha \U0001f600 Omega\n' for i in range(180))
    source_bytes = source.encode('utf-8')
    assert (directory / 'synthetic-input.txt').read_bytes() == source_bytes
    assert report['synthetic_input_sha256'] == sha(source_bytes)
    assert report['synthetic_input_utf16_units'] == units(source)
    # Public packages retain selected synthetic control lines, not the raw log.
    serial_path = directory / 'serial.log'
    if not serial_path.exists():
        serial_path = directory / 'serial-selected.log'
    serial = serial_path.read_bytes()
    assert len(set(report['processes'][k] for k in ('parent', 'provider', 'consumer'))) == 3
    assert report['resources_before'] == report['resources_after']
    assert b'SSG_SESSION consumer_wait=0 outcome=1 code=0' in serial
    assert b'SSG_SESSION provider_wait=0 outcome=1 code=0' in serial
    requests, responses = {}, {}
    for path in directory.glob('*-req.bin'):
        requests[int(path.name.split('-')[0])] = json.loads(path.read_bytes())
    for path in directory.glob('*-resp.bin'):
        responses[int(path.name.split('-')[0])] = json.loads(path.read_bytes())
    assert requests and requests.keys() == responses.keys()
    assert sorted(requests) == list(range(1, len(requests) + 1))
    instance = report['processes']['instance']
    assert report['owner_documents'][0] == {'units': units(source), 'sha256': sha(source_bytes)}
    snapshots = sorted(i for i, req in requests.items() if req['op'] == 'snapshot')
    assert snapshots and snapshots[0] == 1
    initial = responses[1]
    assert initial['status'] == 'OK' and initial['sourceInstance'] == instance
    assert initial['providerPid'] == str(report['processes']['provider'])
    node = next(n for n in initial['nodes'] if n.get('nativeName') == 'document')
    epoch, node_id = initial['sourceEpoch'], node['id']
    ranges = [(i, requests[i], responses[i]) for i in sorted(requests) if requests[i]['op'] == 'text_range']
    assert len(ranges) >= 3
    old = ranges[:2]
    assert [(r['start'], r['end']) for _, _, r in old] == [(0, 511), (511, 1023)]
    old_revision = old[0][2]['documentRevision']
    for _, req, resp in old:
        assert resp['status'] == 'OK' and resp['sourceInstance'] == instance
        assert req['sourceEpoch'] == epoch and req['nodeId'] == node_id
        assert resp['sourceEpoch'] == epoch and resp['nodeId'] == node_id
        assert resp['documentRevision'] == old_revision
        assert resp['text'] == utf16_slice(source, resp['start'], resp['end'])
        assert units(resp['text']) == resp['end'] - resp['start']
    ready = serial.index(b'SSG_NOTES_EDIT_INJECTION_READY')
    markers = report['transaction_markers']
    result = {'case': case, 'status': 'PASSED', 'input_sha256': sha(source_bytes),
              'initial_revision': old_revision, 'initial_pages_utf16': [[r['start'], r['end']] for _, _, r in old],
              'initial_staged_utf16_units': old[-1][2]['end'], 'resources_restored': True,
              'provider_pid': report['processes']['provider'], 'consumer_pid': report['processes']['consumer']}
    if case in ('edit', 'no-edit'):
        expected = ('z' if case == 'edit' else '') + source
        if case == 'edit':
            assert serial.index(b'EDITOR_CHANGE', ready) > ready
            reset = [(i, req, resp) for i, req, resp in ranges if resp['status'] == 'RESET_REQUIRED']
            assert len(reset) == 1
            seq, req, resp = reset[0]
            assert req['start'] == 1023 and req['documentRevision'] == old_revision
            assert resp['sourceInstance'] == instance and resp['documentRevision'] != old_revision
            assert requests[seq + 1]['op'] == 'snapshot'
            assert serial.index(b'SSG_TEXT_TRANSACTION DISCARDED', ready) > serial.index(b'EDITOR_CHANGE', ready)
            committed = [(i, q, r) for i, q, r in ranges if i > seq and r['status'] == 'OK']
            revision = resp['documentRevision']
            assert len(report['owner_documents']) >= 2
            assert report['owner_documents'][-1] == {'units': units(expected), 'sha256': sha(expected.encode())}
            result.update(reset_count=1, final_revision=revision, owner_digest_matches=True)
        else:
            assert not any(r['status'] == 'RESET_REQUIRED' for _, _, r in ranges)
            assert all('INVALID' not in marker and 'DISCARDED' not in marker for marker in markers)
            assert len(report['owner_documents']) == 1
            committed, revision = ranges, old_revision
            result.update(reset_count=0, final_revision=revision, owner_digest_matches=True)
        position = 0
        assembled = ''
        for _, req, resp in committed:
            assert resp['status'] == 'OK' and req['start'] == position == resp['start']
            assert req['sourceInstance'] == resp['sourceInstance'] == instance
            assert req['sourceEpoch'] == resp['sourceEpoch'] == epoch
            assert req['nodeId'] == resp['nodeId'] == node_id
            assert resp['documentRevision'] == revision and resp['documentLength'] == units(expected)
            if position:
                assert req['documentRevision'] == revision
            assert resp['text'] == utf16_slice(expected, resp['start'], resp['end'])
            assert units(resp['text']) == resp['end'] - resp['start']
            assert resp['remaining'] == units(expected) - resp['end']
            assembled += resp['text']
            position = resp['end']
        assert position == units(expected) and assembled == expected
        assert (directory / '00-text.bin').read_bytes() == expected.encode()
        assert (expected.count('z') == 1) if case == 'edit' else ('z' not in expected)
        result.update(final_utf16_units=position, final_sha256=sha(expected.encode()),
                      final_pages=len(committed), no_mixed_revision=True)
    else:
        expected_status = 'DENIED' if case == 'revoke' else 'PROTECTED'
        restricted = ranges[2:]
        assert len(restricted) == 2
        assert all(resp['status'] == expected_status and 'text' not in resp for _, _, resp in restricted)
        assert restricted[0][1]['start'] == 1023 and restricted[0][1]['documentRevision'] == old_revision
        assert restricted[1][1]['start'] == 0 and 'documentRevision' not in restricted[1][1]
        assert all(resp['sourceInstance'] == instance for _, _, resp in restricted)
        assert not (directory / '00-text.bin').exists()
        assert any('DISCARDED units=1023 reason=' + expected_status in marker for marker in markers)
        assert any('REFUSAL_CONFIRMED status=' + expected_status in marker for marker in markers)
        event = {'revoke': b'SSG_TEST_OWNER_REVOKED',
                 'protect-document': b'SSG_TEST_OWNER_DOCUMENT_PROTECTED',
                 'protect-ancestor': b'SSG_TEST_OWNER_ANCESTOR_PROTECTED'}[case]
        assert serial.index(event, ready) > ready
        assert serial.index(b'SSG_TEXT_TRANSACTION DISCARDED', ready) > serial.index(event, ready)
        result.update(refusal=expected_status, refusal_responses=2,
                      post_restriction_text_returned=False, staging_committed=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    (args.directory / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
