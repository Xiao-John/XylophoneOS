#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independently rebuild both IPC streams and compare the guest aggregate."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
from ssg_browser_structure import decode_capture, validate_oracle, compare_structure


def require(value, message):
    if not value:
        raise AssertionError(message)


def check_source_metadata(source):
    require(source.get('slot') in ('browser', 'notes') and isinstance(source.get('scope'), str) and source['scope'] and
            isinstance(source.get('presentation'), str) and source['presentation'], 'source scope missing')
    start, end = source.get('startedMonotonicNs'), source.get('endedMonotonicNs')
    require(isinstance(start, str) and start.isdigit() and isinstance(end, str) and end.isdigit() and int(start) <= int(end), 'source observation interval missing')
    require(isinstance(source.get('instance'), str) and re.fullmatch(r'[0-9a-f]{32}', source['instance']), 'source instance missing')
    if source.get('status') == 'OBSERVED_COMPLETE':
        expected = 'LOCALLY_COMPLETE_ORACLE_REQUIRED' if source['slot'] == 'browser' else 'REVISION_CONSISTENT_OWNER_ORACLE_REQUIRED'
        require(source.get('completeness') == expected and source.get('freshness') == 'UNVERIFIED_AFTER_OBSERVATION' and isinstance(source.get('epoch'), str) and source['epoch'] and
                isinstance(source.get('revision'), str) and source['revision'], 'complete source metadata missing')
    else:
        require(source.get('completeness') == 'NOT_OBSERVED' and source.get('freshness') == 'NOT_CURRENT' and source.get('epoch') is None and source.get('revision') is None and
                isinstance(source.get('failure'), str) and source['failure'], 'failed source metadata missing or stale')


def check_wiring(serial, report, sources):
    require(report.get('status') == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'guest runner did not complete successfully')
    expected_code = 1 if report.get('case') in ('notes-denied', 'default-denied') else 0
    require(report.get('supervisor_exit') == {'kind': 'exited', 'code': expected_code}, 'supervisor exit status was not expected')
    pids = report['processes']
    require(len(set(pids.values())) == 3, 'process roles are not distinct')
    case = report.get('case')
    browser_granted = case not in ('browser-denied', 'default-denied')
    notes_granted = case not in ('notes-denied', 'default-denied')
    require(('P3B_SCOPE browser_text=%d notes_text=%d' % (browser_granted, notes_granted)).encode() in serial,
            'explicit source scope marker missing')
    for slot in ('browser', 'notes'):
        pid = str(pids[slot]).encode()
        supervisor = str(pids['supervisor']).encode()
        instance = sources[slot]['instance'].encode()
        require(re.search(rb'\[process\] event=started pid=' + pid + rb' parent=' + supervisor + rb'\b', serial), 'kernel child-start record missing')
        require(re.search(rb'P3B_SOURCE slot=' + slot.encode() + rb' supervisor=' + supervisor + rb' provider=' + pid + rb' instance=' + instance + rb' channel=independent\b', serial), 'parent wiring record missing')
        require(re.search(rb'SSG_PROVIDER_READY pid=' + pid + rb' instance=' + instance + rb'\b', serial), 'provider readiness missing')


def frames(serial):
    pattern = re.compile(rb'^P3B_FRAME_(BEGIN|PART|END) (browser|notes|aggregate) (REQ|RESP|BASELINE) (\d+)(?: (.*))?$')
    pending, seen, result = {}, set(), []
    for line in serial.splitlines():
        match = pattern.fullmatch(line)
        if not match:
            require(not line.startswith(b'P3B_FRAME_'), 'malformed frame record')
            continue
        kind, slot, direction, sequence, rest = match.groups()
        key = (slot.decode(), direction.decode(), int(sequence))
        if kind == b'BEGIN':
            require(key not in seen and rest is not None, 'duplicate or incomplete begin')
            length, encoded = map(int, rest.split())
            maximum = 4 * 1024 * 1024 if key[0] == 'aggregate' else 4096 if key[1] == 'REQ' else 81920
            require(0 < length <= maximum and encoded == 4 * ((length + 2) // 3), 'invalid frame bound')
            pending[key] = [length, encoded, bytearray()]
            seen.add(key)
        elif kind == b'PART':
            require(key in pending and rest is not None, 'orphan part')
            pos, chunk = rest.split(b' ', 1)
            require(int(pos) == len(pending[key][2]), 'noncontiguous frame part')
            pending[key][2].extend(chunk)
            require(len(pending[key][2]) <= pending[key][1], 'oversized encoded frame')
        else:
            require(key in pending and rest is None, 'orphan end')
            length, encoded_length, encoded = pending.pop(key)
            require(len(encoded) == encoded_length, 'incomplete frame')
            data = base64.b64decode(encoded, validate=True)
            require(len(data) == length, 'invalid payload length')
            result.append((key, json.loads(data)))
    require(not pending, 'unfinished frame')
    return dict(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--browser-receipt', type=Path, required=True)
    a = p.parse_args()
    out = a.output
    report = json.loads((out / 'report.json').read_text())
    serial = (out / 'serial.log').read_bytes()
    budget = re.search(rb'P3B_BUDGET browser_remaining_ns=(\d+) notes_before_ns=(\d+)', serial)
    require(budget and 0 < int(budget[1]) < 300000000000 and int(budget[2]) == 300000000000, 'source budgets were not independent')
    f = frames(serial)
    aggregate = f[('aggregate', 'BASELINE', 0)]
    sources = {s['slot']: s for s in aggregate['sources']}
    require(set(sources) == {'browser', 'notes'}, 'unexpected source slots')
    for source in sources.values():
        check_source_metadata(source)
    check_wiring(serial, report, sources)
    require(aggregate['semantics'] == 'sequential-per-source-non-atomic' and aggregate['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'snapshot semantics missing')
    pids = report['processes']
    require(len(set(pids.values())) == 3, 'process roles are not distinct')
    receipt = json.loads(a.browser_receipt.read_text())
    require(receipt.get('test_structure_oracle') is True and receipt.get('elf_sha256') == report['inputs']['browser']['sha256'], 'oracle build mismatch')
    root = Path(__file__).resolve().parents[1]
    for name in ('build.py', 'main.cpp', 'view.hpp', 'test_structure_oracle.hpp', 'content.hpp', 'scene_geometry.hpp'):
        rel = 'src/ports/aurora_browser/' + name
        matches = [v for k, v in receipt['inputs'].items() if k.endswith('/' + rel)]
        require(matches == [hashlib.sha256((root / rel).read_bytes()).hexdigest()], 'oracle source mismatch: ' + rel)
    oracles = decode_capture(serial)['oracles']
    require(len(oracles) == 2, 'expected before and after oracle')
    before, after = [x['data'] for x in oracles]
    reference = validate_oracle(before, report['inputs']['input']['sha256'], 'before')
    validate_oracle(after, report['inputs']['input']['sha256'], 'after')
    for field in ('document', 'inputSha256', 'sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision', 'nodeCount', 'structureSha256', 'nodes'):
        require(before[field] == after[field], 'oracle changed: ' + field)
    require(before['providerPid'] == str(pids['browser']), 'oracle PID mismatch')
    br = sorted((seq, value) for (slot, direction, seq), value in f.items() if slot == 'browser' and direction == 'RESP')
    bq = sorted((seq, value) for (slot, direction, seq), value in f.items() if slot == 'browser' and direction == 'REQ')
    require(br and [i for i, _ in br] == [i for i, _ in bq] == list(range(1, len(br) + 1)), 'browser frames not paired')
    nodes, cursor, session = [], None, None
    for (seq, req), (_, resp) in zip(bq, br):
        require(req.get('op') == ('snapshot_begin' if seq == 1 else 'snapshot_next'), 'browser request operation')
        if seq > 1:
            require(req.get('cursor') == cursor and req.get('sourceInstance') == before['sourceInstance'], 'cursor continuity')
        for field in ('sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision'):
            require(resp.get(field) == before[field], 'browser source mismatch: ' + field)
        require(resp.get('status') == 'OK' and resp.get('pageSequence') == str(seq) and resp.get('sourceValid') is True and resp.get('query') == '' and resp.get('visibleOnly') is False, 'invalid browser page')
        if session is None:
            session = resp.get('sessionId')
        require(session and resp.get('sessionId') == session, 'mixed browser sessions')
        complete = seq == len(br)
        require(resp.get('complete') is complete and resp.get('traversalComplete') is complete and resp.get('hasNext') is (not complete), 'bad completion')
        cursor = resp.get('cursor')
        require((cursor == '') if complete else (isinstance(cursor, str) and bool(cursor)), 'bad cursor')
        nodes.extend(resp['nodes'])
    compare_structure(reference, nodes)
    browser = sources['browser']
    require(browser['status'] == 'OBSERVED_COMPLETE' and browser['instance'] == before['sourceInstance'] and browser['epoch'] == before['sourceEpoch'] and browser['revision'] == before['sourceRevision'] and browser['session'] == session, 'browser aggregate identity mismatch')
    require(len(browser['nodes']) == len(nodes), 'browser aggregate node count mismatch')
    for raw, combined in zip(nodes, browser['nodes']):
        require(combined['id'] == {'slot': 'browser', 'sourceInstance': before['sourceInstance'], 'sourceEpoch': before['sourceEpoch'], 'localNodeId': raw['id']}, 'browser global identity mismatch')
        for field in ('parent', 'role', 'tag', 'text', 'href'):
            require((field in raw) == (field in combined) and raw.get(field) == combined.get(field), 'browser aggregate differs: ' + field)
    nq = sorted((seq, value) for (slot, direction, seq), value in f.items() if slot == 'notes' and direction == 'REQ')
    nr = sorted((seq, value) for (slot, direction, seq), value in f.items() if slot == 'notes' and direction == 'RESP')
    require(nq and [i for i, _ in nq] == [i for i, _ in nr] == list(range(1, len(nq) + 1)), 'notes frames not paired')
    snap = nr[0][1]
    require(nq[0][1].get('op') == 'snapshot' and snap['status'] == 'OK' and snap['providerPid'] == str(pids['notes']), 'notes snapshot mismatch')
    node = snap['nodes'][0]
    notes = sources['notes']
    if report['case'] == 'notes-denied':
        require(aggregate['status'] == 'AGGREGATE_PARTIAL' and notes['status'] == 'DENIED', 'denial not represented')
        require(node.get('textStatus') == 'NOT_AUTHORIZED' and 'text' not in node and all('text' not in resp for _, resp in nr), 'denied text leaked')
    else:
        require(aggregate['status'] == 'AGGREGATE_COMPLETE_OBSERVED' and notes['status'] == 'OBSERVED_COMPLETE', 'incomplete aggregate')
        text, offset, revision = '', 0, None
        for (_, req), (_, part) in zip(nq[1:], nr[1:]):
            require(req.get('op') == 'text_range' and req.get('start') == offset and part.get('status') == 'OK', 'range sequence')
            require(part['providerPid'] == str(pids['notes']) and part['sourceInstance'] == snap['sourceInstance'] and part['sourceEpoch'] == snap['sourceEpoch'] and part['nodeId'] == node['id'], 'range source mismatch')
            if revision is None:
                revision = part['documentRevision']
            require(part['documentRevision'] == revision and (offset == 0 or req.get('documentRevision') == revision), 'mixed document revision')
            value = part['text']
            units = len(value.encode('utf-16-le')) // 2
            require(part['start'] == offset and part['end'] == offset + units and part['indexUnit'] == 'UTF-16-code-unit', 'range boundary mismatch')
            offset = part['end']
            require(part['remaining'] == part['documentLength'] - offset, 'remaining mismatch')
            text += value
        expected = (out / 'synthetic-input.txt').read_text()
        require(text == expected and offset == len(expected.encode('utf-16-le')) // 2 and offset == part['documentLength'], 'synthetic document mismatch')
        doc = notes['document']
        require(doc['text'] == text and doc['utf16Units'] == offset and notes['revision'] == revision, 'aggregate text mismatch')
        require(doc['id'] == {'slot': 'notes', 'sourceInstance': snap['sourceInstance'], 'sourceEpoch': snap['sourceEpoch'], 'localNodeId': node['id']}, 'notes global identity mismatch')
        digest = hashlib.sha256(expected.encode()).hexdigest().encode()
        require(re.search(rb'SSG_TEST_OWNER_DOCUMENT units=' + str(offset).encode() + rb' sha256=' + digest + rb'\b', serial) is not None, 'owner document digest mismatch')
        local_collisions = [n['id'] for n in browser['nodes'] if n['id']['localNodeId'] == doc['id']['localNodeId']]
        require(notes['instance'] != browser['instance'] and local_collisions and all(identity != doc['id'] for identity in local_collisions),
                'overlapping local node ID was not separated by source namespace')
    require(int(browser['endedMonotonicNs']) <= int(notes.get('startedMonotonicNs', browser['endedMonotonicNs'])), 'observation order mismatch')
    result = {'status': 'PASSED_SCOPED', 'browser_nodes': len(nodes), 'browser_pages': len(br), 'notes_responses': len(nr),
              'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'notes_utf16_units': offset if report['case'] != 'notes-denied' else None,
              'overlapping_local_id_namespaced': report['case'] != 'notes-denied',
              'global_atomic_snapshot': 'NOT_IMPLEMENTED', 'oracle': 'independent liteHTML model and synthetic owner digest',
              'resources_restored': report['resources_restored'], 'source_exits': report['source_exits']}
    (out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
