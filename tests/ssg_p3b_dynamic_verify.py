#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check both aggregate samples, independent DOMs and Notes transaction history."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_browser_structure import decode_capture, validate_oracle, compare_structure


def verify_browser_receipt(path, report):
    receipt = json.loads(path.read_text())
    require(receipt.get('test_structure_oracle') is True and receipt.get('elf_sha256') == report['inputs']['browser']['sha256'], 'browser receipt mismatch')
    root = Path(__file__).resolve().parents[1]
    for name in ('build.py', 'main.cpp', 'view.hpp', 'test_structure_oracle.hpp', 'content.hpp', 'scene_geometry.hpp'):
        rel = 'src/ports/aurora_browser/' + name
        require([v for k, v in receipt['inputs'].items() if k.endswith('/' + rel)] == [hashlib.sha256((root / rel).read_bytes()).hexdigest()], 'browser source mismatch')


def verify_qmp_key(report, serial, ready, code, observed):
    ready_at = serial.find(ready)
    observed_at = serial.find(observed, max(0, ready_at))
    matches = []
    for event in report.get('qmp_events', []):
        for item in (event.get('arguments') or {}).get('events', []):
            data = item.get('data', {})
            if item.get('type') == 'key' and data.get('down') is True and data.get('key', {}).get('data') == code:
                matches.append(event.get('serial_offset'))
    require(ready_at >= 0 and observed_at > ready_at and any(isinstance(n, int) and ready_at <= n <= observed_at for n in matches), 'QMP/guest input order mismatch')


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
    code, observed = {'edit': ('z', b'EDITOR_CHANGE'), 'revoke': ('6', b'SSG_TEST_OWNER_REVOKED'),
                      'protect-document': ('7', b'SSG_TEST_OWNER_DOCUMENT_PROTECTED'),
                      'protect-ancestor': ('8', b'SSG_TEST_OWNER_ANCESTOR_PROTECTED')}[report['case']]
    verify_qmp_key(report, serial, b'P3B_EDIT_INJECTION_READY', code, observed)
    data = frames(serial)
    aggs = [data[('aggregate', 'BASELINE', i)] for i in (0, 1)]
    for agg in aggs:
        require(agg['semantics'] == 'sequential-per-source-non-atomic' and agg['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED', 'aggregate semantics')
    sources = [{s['slot']: s for s in agg['sources']} for agg in aggs]
    for sample in sources:
        for source in sample.values(): check_source_metadata(source)
    check_wiring(serial, report, sources[0])
    require(aggs[0]['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'missing baseline A')
    verify_browser_receipt(a.browser_receipt, report)
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
    decoded = [notes_segment(s, report['processes']['notes']) for s in segments[:3]]
    original = (out / 'synthetic-input.txt').read_text()
    base, node, first, revision, failure = decoded[0]
    require(first == original and failure is None, 'baseline A notes mismatch')
    doc = sources[0]['notes']['document']
    require(doc['text'] == original and sources[0]['notes']['revision'] == revision, 'baseline A aggregate mismatch')
    require(doc['id'] == {'slot': 'notes', 'sourceInstance': base['sourceInstance'], 'sourceEpoch': base['sourceEpoch'], 'localNodeId': node['id']}, 'notes namespace mismatch')
    require(base['sourceInstance'] != a_oracle['sourceInstance'], 'source instances collide')
    require(decoded[1][0]['sourceInstance'] == base['sourceInstance'] and decoded[1][0]['sourceEpoch'] == base['sourceEpoch'] and decoded[1][1]['id'] == node['id'], 'staging source changed')
    require(decoded[1][2] and decoded[1][2] == original[:len(decoded[1][2])], 'missing old-revision staging')
    if report['case'] == 'edit':
        require(len(segments) == 3, 'unexpected edit transaction sequence')
        require(b'EDITOR_KEY key=90' in serial and b'EDITOR_CHANGE' in serial, 'guest did not receive the edit key')
        require(decoded[1][4] == 'RESET_REQUIRED' and b'P3B_NOTES_DISCARD reason=RESET_REQUIRED' in serial, 'old revision not discarded')
        newer = decoded[-1]
        require(newer[4] is None and newer[2] == 'z' + original and newer[3] != revision, 'new revision text mismatch')
        require(sources[1]['notes']['document']['text'] == newer[2] and sources[1]['notes']['revision'] == newer[3], 'baseline B notes mismatch')
        require(newer[0]['sourceInstance'] == base['sourceInstance'] and newer[0]['sourceEpoch'] == base['sourceEpoch'] and newer[1]['id'] == node['id'], 'new revision belongs to another document')
        require(aggs[1]['status'] == 'AGGREGATE_COMPLETE_OBSERVED', 'baseline B incomplete')
        expected = newer[2]
        require(b'P3B_DIFF browser=UNCHANGED notes=CHANGED' in serial, 'aggregate diff missing')
    else:
        status = 'DENIED' if report['case'] == 'revoke' else 'PROTECTED'
        require(len(segments) == 5, 'missing alternative-role or fresh-range probes')
        require(decoded[1][4] == status, 'mid-range refusal missing')
        require(decoded[-1][1].get('textStatus') == ('NOT_AUTHORIZED' if status == 'DENIED' else 'PROTECTED'), 'fresh snapshot bypassed restriction')
        require('text' not in decoded[-1][1], 'fresh restricted snapshot leaked text')
        require(aggs[1]['status'] == 'AGGREGATE_PARTIAL' and sources[1]['notes']['status'] == status and 'document' not in sources[1]['notes'], 'restricted aggregate leaked or claimed completion')
        require(('P3B_DIFF browser=UNCHANGED notes=' + status + ' retry_refused=1').encode() in serial, 'independent source/refusal diff missing')
        require(('P3B_ALTERNATE_REFUSAL status=' + status + ' no_text=1 label_safe=1 range_refused=1').encode() in serial, 'alternative-role refusal missing')
        probe_doc = segments[3][0][1]
        require(len(probe_doc.get('nodes', [])) == 1 and 'text' not in probe_doc['nodes'][0] and probe_doc['nodes'][0].get('textStatus') == ('NOT_AUTHORIZED' if status == 'DENIED' else 'PROTECTED'), 'refreshed document leaked text')
        require(segments[4][0][0].get('role') == 'label' and segments[4][0][1].get('status') == 'OK', 'alternative role probe missing')
        require(original[:32] not in json.dumps(segments[4][0][1], ensure_ascii=False), 'alternative role leaked document text')
        direct_req, direct_resp = segments[4][-1]
        require(direct_req.get('op') == 'text_range' and direct_resp.get('status') == status and 'text' not in direct_resp, 'fresh range bypassed restriction')
        expected = original
    changes = re.findall(rb'^P3B_AGGREGATE_DIFF (\{.*\})\r?$', serial, re.MULTILINE)
    require(len(changes) == 1, 'aggregate Diff missing')
    changes = json.loads(changes[0])
    require(changes == {'status': 'OK', 'semantics': 'per-source-non-atomic', 'browser': 'UNCHANGED',
                        'notes': 'CHANGED' if report['case'] == 'edit' else 'PERMISSION_CHANGED'}, 'aggregate Diff classification')
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
