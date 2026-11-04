#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independently verify watch events against captured IPC, owner and QMP records."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from ssg_p3b_verify import frames, require, check_source_metadata, check_wiring
from ssg_p3b_dynamic_verify import check_browser, notes_segment, verify_browser_receipt
from ssg_browser_structure import decode_capture
from ssg_watch_events import decode_event_records


def groups(data, slot, begin):
    requests = sorted((seq, value) for (s, direction, seq), value in data.items() if s == slot and direction == 'REQ')
    responses = sorted((seq, value) for (s, direction, seq), value in data.items() if s == slot and direction == 'RESP')
    require([seq for seq, _ in requests] == [seq for seq, _ in responses] == list(range(1, len(requests) + 1)), 'unpaired ' + slot + ' frames')
    result = []
    for (_, request), (_, response) in zip(requests, responses):
        if request.get('op') == 'detail':
            require(response.get('status') == 'SOURCE_REPLACED' and 'node' not in response, 'old browser reference accepted')
            continue
        if request.get('op') == begin:
            result.append([])
        require(result, 'request precedes snapshot')
        result[-1].append((request, response))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--require-structured', action='store_true', help='require the current structured identity namespace')
    a = p.parse_args()
    out = a.output
    report = json.loads((out / 'report.json').read_text())
    require(report['status'] == 'OBSERVED_PENDING_INDEPENDENT_VERIFICATION', 'guest did not complete')
    serial = (out / 'serial.log').read_bytes()
    f = frames(serial)
    cycle_count = 2 if report['case'] == 'stop' else 3
    samples = [f[('aggregate', 'BASELINE', i)] for i in range(1, cycle_count + 1)]
    sources = [{s['slot']: s for s in sample['sources']} for sample in samples]
    for sample, pair in zip(samples, sources):
        require(sample['globalAtomicSnapshot'] == 'NOT_IMPLEMENTED' and sample['semantics'] == 'sequential-per-source-non-atomic', 'incorrect global time claim')
        require(set(pair) == {'browser', 'notes'}, 'source slots')
        for source in pair.values():
            check_source_metadata(source)
    check_wiring(serial, report, sources[0])
    verify_browser_receipt(out / 'browser.receipt.json', report)
    original = (out / 'synthetic-input.txt').read_text()
    event_records = decode_event_records(serial)
    require(len({record['stream'] for record in event_records}) == 1, 'unexpected watch stream count')
    events = [record['data'] for record in event_records]
    require(len(events) == 2 * cycle_count, 'missing event')
    namespace_formats = set()
    for index, event in enumerate(events):
        slot = ('browser', 'notes')[index % 2]
        cycle = index // 2
        source = sources[cycle][slot]
        require(event['slot'] == slot and event['sequence'] == str(cycle + 1), 'source sequence or slot')
        namespace = {'slot': slot, 'source_instance': source['instance'], 'source_epoch': source['epoch'] or ''}
        actual_namespace = event['identity_namespace']
        if isinstance(actual_namespace, dict):
            namespace_formats.add('structured')
            require(actual_namespace == namespace, 'source namespace')
        else:
            # Exploratory older captures used a string; report the format so a
            # current structured-contract result cannot be confused with it.
            namespace_formats.add('legacy_string')
            legacy = slot + ':' + source['instance'] + (':' + source['epoch'] if source['epoch'] else '')
            require(actual_namespace == legacy, 'legacy source namespace')
        require(event['source_instance'] == source['instance'], 'source instance')
        require(event['source_epoch'] == (source['epoch'] or ''), 'event epoch differs from observation')
        require(event['source_revision_after'] == (source['revision'] or ''), 'event revision differs from observation')
        require(event['source_revision_before'] == ((sources[cycle - 1][slot]['revision'] or '') if cycle else ''), 'previous revision is not source-local')
        require(event['observation_scope'] == source['scope'] and event['presentation_state'] == source['presentation'], 'scope or presentation mismatch')
        require(event['observation_start'] == source['startedMonotonicNs'] and event['observation_end'] == source['endedMonotonicNs'], 'event interval differs from observation')
        require(int(event['observation_start']) <= int(event['observation_end']) and event['capability_set'], 'invalid observation metadata')
        if slot == 'notes':
            require(event['capability_set'].get('geometry') == 'UNSUPPORTED' and 'geometry_changes' not in event['summary'], 'invented Notes geometry')
        require(original[:64] not in json.dumps(event, ensure_ascii=False), 'event republishes document text')
    if a.require_structured:
        require(namespace_formats == {'structured'}, 'current structured namespace required')
    for entry in report['events']:
        ready = serial.find(('P3C_CYCLE_READY cycle=%d ' % entry['cycle']).encode())
        next_ready = serial.find(('P3C_CYCLE_READY cycle=%d ' % (entry['cycle'] + 1)).encode(), ready + 1)
        require(ready >= 0 and ready <= entry['serial_offset'] < next_ready, 'PS/2 input is outside the intended observation interval')
        require(any(e.get('command') == 'input-send-event' and entry['serial_offset'] <= e.get('serial_offset', -1) < next_ready and
            any(x.get('type') == 'key' and x.get('data', {}).get('down') is True and
                x.get('data', {}).get('key', {}).get('data') == entry['key'] for x in (e.get('arguments') or {}).get('events', []))
            for e in report['qmp_events']), 'missing recorded QMP key')

    browser_groups = groups(f, 'browser', 'snapshot_begin')
    oracle = decode_capture(serial)['oracles']
    live_browser = [pair['browser'] for pair in sources if pair['browser']['status'] == 'OBSERVED_COMPLETE']
    require(len(browser_groups) == len(live_browser) and len(oracle) == 2 * len(live_browser), 'missing browser captures or independent oracles')
    browser_raw = []
    for i, (records, source) in enumerate(zip(browser_groups, live_browser)):
        check_browser(records, oracle[2*i:2*i+2], source, report)
        require(all(response['scrollY'] == source['scrollY'] for _, response in records), 'Browser scroll differs from IPC')
        raw_nodes = [node for _, response in records for node in response['nodes']]
        for raw, observed in zip(raw_nodes, source['nodes']):
            for field in ('bounds', 'visibleBounds', 'fragments', 'visibleFragments', 'visibility', 'fragmentsComplete'):
                require(raw.get(field) == observed.get(field), 'Browser geometry differs from IPC')
        browser_raw.append(raw_nodes)

    note_groups = []
    pending_capped = 0
    for group in groups(f, 'notes', 'snapshot'):
        if group[0][1].get('capped') is True:
            require(len(group) == 1, 'capped provisional snapshot had range requests')
            pending_capped += 1
        else:
            note_groups.append((pending_capped, group))
            pending_capped = 0
    live_notes = [(index, pair['notes']) for index, pair in enumerate(sources) if pair['notes']['status'] != 'UNAVAILABLE']
    require(pending_capped == 0 and len(note_groups) == len(live_notes), 'missing Notes captures')
    require(serial.count(b'P3C_NOTES_RETRY reason=CAPPED') == sum(count for count, _ in note_groups), 'capped retry log mismatch')
    texts, revisions = [], []
    for (retry_count, records), (index, source) in zip(note_groups, live_notes):
        require(events[2*index+1].get('retry_count', 0) == retry_count, 'event retry count differs from IPC')
        base, node, text, revision, failure = notes_segment(records, report['processes']['notes'])
        if source['status'] == 'OBSERVED_COMPLETE':
            require(failure is None and source['document']['text'] == text and source['revision'] == revision, 'notes transaction or revision mismatch')
            require(source['document']['utf16Units'] == len(text.encode('utf-16-le')) // 2, 'notes UTF-16 length')
            digest = hashlib.sha256(text.encode()).hexdigest().encode()
            require(re.search(rb'SSG_TEST_OWNER_DOCUMENT units=' + str(source['document']['utf16Units']).encode() + rb' sha256=' + digest + rb'\b', serial), 'owner digest mismatch')
            texts.append(text);revisions.append(revision)
        else:
            require(source['status'] in ('DENIED', 'PROTECTED') and 'document' not in source, 'restriction not enforced')
            require(node.get('textStatus') == ('NOT_AUTHORIZED' if source['status'] == 'DENIED' else 'PROTECTED') and 'text' not in node, 'restricted snapshot returned text')
            require(all('text' not in response for _, response in records), 'restricted transaction returned text')

    browser_events = events[::2];note_events = events[1::2]
    case = report['case']
    if case == 'edit':
        require(texts == [original, 'z' + original, 'zx' + original] and len(set(revisions)) == 3, 'two edits or revisions lost')
        require([e['event_type'] for e in note_events] == ['SOURCE_UNKNOWN', 'SOURCE_CHANGED', 'SOURCE_CHANGED'], 'notes change events')
        require(all(e['event_type'] == 'SOURCE_UNCHANGED' for e in browser_events[1:]), 'unrelated Browser changed')
    elif case == 'scroll':
        require(len(browser_raw) == 3, 'scroll captures')
        for i in (1, 2):
            old, new = browser_raw[i-1], browser_raw[i]
            require(len(old) == len(new), 'scroll changed tree length')
            geometry = sum(x['bounds'] != y['bounds'] or x['fragments'] != y['fragments'] for x, y in zip(old, new))
            visibility = sum(x['visibility'] != y['visibility'] or x['visibleBounds'] != y['visibleBounds'] or x['visibleFragments'] != y['visibleFragments'] for x, y in zip(old, new))
            other = sum(int(x.get('text') != y.get('text')) + int(x.get('href') != y.get('href')) for x, y in zip(old, new))
            summary = browser_events[i]['summary']
            require(browser_events[i]['event_type'] == 'SOURCE_CHANGED' and summary['scroll_before'] != summary['scroll_after'] and
                    summary['scroll_before'] == sources[i-1]['browser']['scrollY'] and summary['scroll_after'] == sources[i]['browser']['scrollY'] and
                    summary['scroll_changes'] == 1 and summary['geometry_changes'] == geometry and summary['visibility_changes'] == visibility and
                    summary['other_changes'] == other, 'scroll diff disagrees with independent IPC')
            require(re.search(rb'BROWSER_SCROLL value=' + str(summary['scroll_after']).encode() + rb'\b', serial), 'owner did not report scroll')
        require(texts == [original] * 3 and len(set(revisions)) == 1 and all(e['event_type'] == 'SOURCE_UNCHANGED' for e in note_events[1:]), 'scroll changed Notes')
    elif case == 'reload':
        require(sources[0]['browser']['epoch'] != sources[1]['browser']['epoch'] and browser_events[1]['event_type'] == 'SOURCE_REPLACED', 'reload did not replace source epoch')
        require(b'P3C_OLD_REFERENCE status=SOURCE_REPLACED' in serial, 'old node reference was not checked')
        require(texts == [original] * 3 and all(e['event_type'] == 'SOURCE_UNCHANGED' for e in note_events[1:]), 'reload changed Notes')
    elif case in ('revoke', 'protect-document', 'protect-ancestor'):
        status = 'DENIED' if case == 'revoke' else 'PROTECTED'
        require([s['notes']['status'] for s in sources] == ['OBSERVED_COMPLETE', status, status], 'restriction did not persist')
        require(note_events[1]['event_type'] == 'PERMISSION_CHANGED' and note_events[2]['event_type'] != 'SOURCE_UNCHANGED', 'restriction events')
        require(all(e['baseline_state'] == 'HISTORICAL_OR_ABSENT' for e in note_events[1:]) and all(e['event_type'] == 'SOURCE_UNCHANGED' for e in browser_events[1:]), 'restriction propagated across sources')
    elif case in ('browser-exit', 'notes-exit'):
        failed, peer = (('browser', 'notes') if case == 'browser-exit' else ('notes', 'browser'))
        failed_events, peer_events = ((browser_events, note_events) if failed == 'browser' else (note_events, browser_events))
        require(all(s[failed]['status'] == 'UNAVAILABLE' and s[peer]['status'] == 'OBSERVED_COMPLETE' for s in sources[1:]), 'source failure isolation')
        require(all(e['event_type'] == 'SOURCE_UNAVAILABLE' for e in failed_events[1:]) and all(e['event_type'] == 'SOURCE_UNCHANGED' for e in peer_events[1:]), 'unavailable source reported unchanged or affected peer')
        require(all(s['status'] == 'AGGREGATE_PARTIAL' for s in samples[1:]), 'partial aggregate missing')
        if case == 'browser-exit':
            require(texts == [original] * cycle_count and len(set(revisions)) == 1, 'Browser exit changed Notes')
    else:
        require(texts == [original] * cycle_count and all(e['event_type'] == 'SOURCE_UNCHANGED' for e in browser_events[1:] + note_events[1:]), 'baseline was not stable')
        if case == 'stop':
            require(b'P3C_TEST_CONTROL sent=1' in serial and b'P3C_WATCH_STOP reason=EXPLICIT_STOP' in serial, 'control pipe did not stop watch')
    if case in ('baseline', 'stop', 'edit', 'revoke', 'protect-document', 'protect-ancestor', 'notes-exit'):
        require(all(nodes == browser_raw[0] for nodes in browser_raw[1:]), 'Browser IPC changed while peer was active')
    wire = re.findall(rb'^P3B_FRAME_BEGIN (browser|notes) (REQ|RESP) \d+ (\d+) \d+\r?$', serial, re.MULTILINE)
    counters = re.findall(rb'^P3C_IPC slot=(browser|notes) requests=(\d+) read_bytes=(\d+) written_bytes=(\d+)\r?$', serial, re.MULTILINE)
    if counters:  # Earlier exploratory binaries did not expose counters.
        require(len(counters) == 2, 'missing source IPC counters')
        for slot, requests, read_bytes, written_bytes in counters:
            req = [int(size) + 12 for source, direction, size in wire if source == slot and direction == b'REQ']
            resp = [int(size) + 12 for source, direction, size in wire if source == slot and direction == b'RESP']
            require(int(requests) == len(req) and int(written_bytes) == sum(req) and int(read_bytes) == sum(resp), 'IPC counters differ from captured frames')
    result = {'status': 'PASSED_SCOPED', 'case': case, 'cycles': cycle_count, 'events': len(events),
              'namespace_formats': sorted(namespace_formats),
              'capped_retries': sum(count for count, _ in note_groups),
              'ipc_requests': sum(direction == b'REQ' for _, direction, _ in wire),
              'ipc_bytes_including_frame_headers': sum(int(size) + 12 for _, _, size in wire),
              'elapsed_seconds': report['elapsed_seconds'], 'resource_samples': report['thread_samples'],
              'resources_restored': report['resources_restored'], 'source_exits': report['source_exits'],
              'global_atomic_snapshot': 'NOT_IMPLEMENTED'}
    (out / 'independent-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
