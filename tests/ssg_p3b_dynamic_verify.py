#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check both aggregate samples, independent DOMs and Notes transaction history."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require
from ssg_browser_structure import decode_capture, validate_oracle, compare_structure


def check_browser(records, oracles, source, report):
    require(len(oracles) == 2, 'missing browser oracle pair')
    before, after = [x['data'] for x in oracles]
    reference = validate_oracle(before, report['inputs']['input']['sha256'], 'before')
    validate_oracle(after, report['inputs']['input']['sha256'], 'after')
    for key in ('document', 'inputSha256', 'sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision', 'nodeCount', 'structureSha256', 'nodes'):
        require(before[key] == after[key], 'browser oracle changed: ' + key)
    require(before['providerPid'] == str(report['processes']['browser']), 'browser PID mismatch')
    nodes, cursor, session = [], None, None
    for i, (request, response) in enumerate(records):
        if i == 0:
            require(request.get('op') == 'snapshot_begin', 'browser begin missing')
        else:
            require(request.get('op') == 'snapshot_next' and request.get('cursor') == cursor and request.get('sourceInstance') == before['sourceInstance'], 'browser cursor mismatch')
        for key in ('sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision'):
            require(response.get(key) == before[key], 'browser page identity mismatch')
        if session is None:
            session = response.get('sessionId')
        require(session and response.get('sessionId') == session and response.get('pageSequence') == str(i + 1), 'mixed browser pages')
        complete = i == len(records) - 1
        require(response.get('status') == 'OK' and response.get('complete') is complete and response.get('traversalComplete') is complete and response.get('hasNext') is (not complete), 'browser incomplete')
        cursor = response.get('cursor')
        require((cursor == '') if complete else bool(cursor), 'browser cursor missing')
        nodes.extend(response['nodes'])
    normalized = compare_structure(reference, nodes)
    require(source['status'] == 'OBSERVED_COMPLETE' and source['instance'] == before['sourceInstance'] and source['epoch'] == before['sourceEpoch'] and source['session'] == session, 'browser aggregate identity')
    require(len(source['nodes']) == len(nodes), 'browser aggregate count')
    for raw, merged in zip(nodes, source['nodes']):
        require(merged['id'] == {'slot': 'browser', 'sourceInstance': before['sourceInstance'], 'sourceEpoch': before['sourceEpoch'], 'localNodeId': raw['id']}, 'browser namespace')
        for key in ('parent', 'role', 'tag', 'text', 'href'):
            require((key in merged) == (key in raw) and merged.get(key) == raw.get(key), 'browser aggregate data')
    return normalized, before


def notes_segment(records, pid):
    require(records[0][0].get('op') == 'snapshot', 'notes snapshot missing')
    base = records[0][1]
    require(base.get('status') == 'OK' and base.get('providerPid') == str(pid) and len(base.get('nodes', [])) == 1, 'invalid notes snapshot')
    node = base['nodes'][0]
    text, offset, revision, failure = '', 0, None, None
    for req, resp in records[1:]:
        require(req.get('op') == 'text_range' and req.get('start') == offset, 'notes range request')
        status = resp.get('status')
        require(resp.get('sourceInstance') == base['sourceInstance'], 'notes instance changed')
        if status != 'OK':
            require('text' not in resp, 'failure returned text')
            failure = status
            break
        require(resp.get('providerPid') == str(pid) and resp.get('sourceEpoch') == base['sourceEpoch'] and resp.get('nodeId') == node['id'], 'notes identity mismatch')
        if revision is None:
            revision = resp.get('documentRevision')
        require(revision and resp.get('documentRevision') == revision and (offset == 0 or req.get('documentRevision') == revision), 'mixed notes revision')
        value = resp['text']
        units = len(value.encode('utf-16-le')) // 2
        require(resp.get('start') == offset and resp.get('end') == offset + units and resp.get('indexUnit') == 'UTF-16-code-unit', 'invalid range')
        offset = resp['end']
        require(resp.get('remaining') == resp.get('documentLength') - offset, 'bad remaining length')
        text += value
    if failure is None and len(records) > 1:
        require(offset == records[-1][1]['documentLength'], 'incomplete notes transaction')
    return base, node, text, revision, failure


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--browser-receipt', type=Path, required=True)
    a = p.parse_args()
    out = a.output
    report = json.loads((out / 'report.json').read_text())
    require(report['case'] in ('edit', 'revoke', 'protect-document', 'protect-ancestor'), 'not a dynamic case')
    serial = (out / 'serial.log').read_bytes()
    require('real_ps2_' + report['case'] in report['events'], 'missing QMP input record')
    require(any(e.get('command') == 'input-send-event' for e in report.get('qmp_events', [])), 'missing QMP events')
    data = frames(serial)
    aggs = [data[('aggregate', 'BASELINE', i)] for i in (0, 1)]
    for agg in aggs:
        require(agg['semantics'] == 'sequential-per-source-non-atomic' and agg['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'aggregate semantics')
    sources = [{s['slot']: s for s in agg['sources']} for agg in aggs]
    require(aggs[0]['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'missing baseline A')
    receipt = json.loads(a.browser_receipt.read_text())
    require(receipt.get('test_structure_oracle') is True and receipt['elf_sha256'] == report['inputs']['browser']['sha256'], 'browser receipt mismatch')
    root = Path(__file__).resolve().parents[1]
    for name in ('build.py', 'main.cpp', 'view.hpp', 'test_structure_oracle.hpp', 'content.hpp', 'scene_geometry.hpp'):
        rel = 'src/ports/aurora_browser/' + name
        require([v for k, v in receipt['inputs'].items() if k.endswith('/' + rel)] == [hashlib.sha256((root / rel).read_bytes()).hexdigest()], 'browser source mismatch')
    os = decode_capture(serial)['oracles']
    require(len(os) == 4, 'expected two oracle pairs')
    pairs = {}
    for slot in ('browser', 'notes'):
        req = sorted((seq, value) for (s, d, seq), value in data.items() if s == slot and d == 'REQ')
        resp = sorted((seq, value) for (s, d, seq), value in data.items() if s == slot and d == 'RESP')
        require([x for x, _ in req] == [x for x, _ in resp] == list(range(1, len(req)+1)), slot + ' frames not paired')
        pairs[slot] = [(q, r) for (_, q), (_, r) in zip(req, resp)]
    starts = [i for i, (q, _) in enumerate(pairs['browser']) if q.get('op') == 'snapshot_begin']
    require(len(starts) == 2 and starts[0] == 0, 'expected two browser captures')
    a_nodes, a_oracle = check_browser(pairs['browser'][:starts[1]], os[:2], sources[0]['browser'], report)
    b_nodes, b_oracle = check_browser(pairs['browser'][starts[1]:], os[2:], sources[1]['browser'], report)
    require(a_nodes == b_nodes and a_oracle['sourceInstance'] == b_oracle['sourceInstance'] and a_oracle['sourceEpoch'] == b_oracle['sourceEpoch'], 'unrelated browser content changed')
    segments = []
    for pair in pairs['notes']:
        if pair[0].get('op') == 'snapshot':
            segments.append([])
        require(segments, 'notes has no snapshot')
        segments[-1].append(pair)
    require(len(segments) >= 3, 'missing notes retry or fresh check')
    decoded = [notes_segment(s, report['processes']['notes']) for s in segments]
    original = (out / 'synthetic-input.txt').read_text()
    base, node, first, revision, failure = decoded[0]
    require(first == original and failure is None, 'baseline A notes mismatch')
    doc = sources[0]['notes']['document']
    require(doc['text'] == original and sources[0]['notes']['revision'] == revision, 'baseline A aggregate mismatch')
    require(decoded[1][2] and decoded[1][2] == original[:len(decoded[1][2])], 'missing old-revision staging')
    if report['case'] == 'edit':
        require(b'EDITOR_KEY key=90' in serial and b'EDITOR_CHANGE' in serial, 'guest did not receive the edit key')
        require(decoded[1][4] == 'RESET_REQUIRED' and b'P3B_NOTES_DISCARD reason=RESET_REQUIRED' in serial, 'old revision not discarded')
        newer = decoded[-1]
        require(newer[4] is None and newer[2] == 'z' + original and newer[3] != revision, 'new revision text mismatch')
        require(sources[1]['notes']['document']['text'] == newer[2] and sources[1]['notes']['revision'] == newer[3], 'baseline B notes mismatch')
        require(aggs[1]['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'baseline B incomplete')
        expected = newer[2]
        require(b'P3B_DIFF browser=UNCHANGED notes=CHANGED' in serial, 'aggregate diff missing')
    else:
        status = 'DENIED' if report['case'] == 'revoke' else 'PROTECTED'
        require(decoded[1][4] == status, 'mid-range refusal missing')
        require(decoded[-1][1].get('textStatus') == ('NOT_AUTHORIZED' if status == 'DENIED' else 'PROTECTED'), 'fresh snapshot bypassed restriction')
        require('text' not in decoded[-1][1], 'fresh restricted snapshot leaked text')
        require(aggs[1]['status'] == 'AGGREGATE_PARTIAL' and sources[1]['notes']['status'] == status and 'document' not in sources[1]['notes'], 'restricted aggregate leaked or claimed completion')
        require(('P3B_DIFF browser=UNCHANGED notes=' + status + ' retry_refused=1').encode() in serial, 'independent source/refusal diff missing')
        expected = original
    digest = hashlib.sha256(expected.encode()).hexdigest().encode()
    units = len(expected.encode('utf-16-le')) // 2
    require(re.search(rb'SSG_TEST_OWNER_DOCUMENT units=' + str(units).encode() + rb' sha256=' + digest + rb'\b', serial), 'owner digest mismatch')
    require(report['resources_restored'], 'resources not restored')
    result = {'status': 'PASSED_SCOPED', 'case': report['case'], 'browser_nodes_each': [len(a_nodes), len(b_nodes)],
              'notes_segments': len(segments), 'real_ps2_input': True, 'browser_presentation': 'hidden-no-input',
              'notes_presentation': 'visible', 'global_atomic_snapshot': 'NOT_IMPLEMENTED',
              'source_exits': report['source_exits'], 'resources_restored': True}
    (out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
