#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent audit of already recorded guest evidence, never a new guest run.

Does not import the production validator and does not parse HTML to infer a DOM.
Decodes the raw serial captures, rebuilds an adjacency tree from IPC parent IDs,
recursively derives paths, compares every record with the guest Oracle, and
recomputes the documented netstring digest. It never starts QEMU or mutates inputs.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from ssg_public_paths import portable


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def records_from_serial(serial):
    pending, records = {}, {}
    offset = 0
    for line_with_end in serial.splitlines(keepends=True):
        line = line_with_end.rstrip(b'\r\n')
        match = re.fullmatch(rb'SSG_(FRAME|ORACLE)_(BEGIN|PART|END) (.*)', line)
        if match is None:
            require(b'SSG_FRAME_' not in line and b'SSG_ORACLE_' not in line,
                    'Malformed record marker')
            offset += len(line_with_end)
            continue
        family, kind, tail = match.groups()
        fields = tail.split(b' ')
        direction = fields.pop(0).decode() if family == b'FRAME' else 'ORACLE'
        sequence = int(fields.pop(0))
        require(direction in ('REQ', 'RESP', 'ORACLE') and sequence > 0,
                'Invalid record identity')
        key = (direction, sequence)
        if kind == b'BEGIN':
            require(key not in pending and key not in records and len(fields) == 2,
                    'Duplicate or invalid record header')
            pending[key] = {'size': int(fields[0]), 'encoded_size': int(fields[1]),
                            'chunks': bytearray(), 'begin': offset}
        elif kind == b'PART':
            require(key in pending and len(fields) == 2, 'Orphan record part')
            state = pending[key]
            require(int(fields[0]) == len(state['chunks']), 'Noncontiguous record part')
            state['chunks'].extend(fields[1])
        else:
            require(key in pending and not fields, 'Orphan or invalid record end')
            state = pending.pop(key)
            require(len(state['chunks']) == state['encoded_size'], 'Encoded length mismatch')
            payload = base64.b64decode(state.pop('chunks'), validate=True)
            require(len(payload) == state['size'], 'Payload length mismatch')
            records[key] = dict(state, payload=payload, data=json.loads(payload),
                                end=offset + len(line_with_end))
        offset += len(line_with_end)
    require(not pending, 'Unterminated serial record')
    return records


def digest_nodes(nodes):
    encoded = bytearray(b'XOS-LITEHTML-STRUCTURE-V1\n')
    fixed = ('path', 'parentPath', 'ordinal', 'childIndex', 'childCount', 'tag', 'role')
    for node in nodes:
        values = [str(node[key]) for key in fixed]
        values.extend((str(int('text' in node)), node.get('text', ''),
                       str(int('href' in node)), node.get('href', '')))
        for value in values:
            data = value.encode('utf-8')
            encoded.extend(str(len(data)).encode() + b':' + data + b',')
        encoded.extend(b'\n')
    return sha(encoded)


def adjacency_reconstruction(nodes):
    if not nodes:
        return []
    ids = {node['id']: node for node in nodes}
    require(len(ids) == len(nodes), 'Duplicate IPC node ID')
    indices = {node['id']: index for index, node in enumerate(nodes)}
    children = {node_id: [] for node_id in ids}
    roots = []
    for index, node in enumerate(nodes):
        if node['parent'] == '0':
            roots.append(node['id'])
        else:
            require(node['parent'] in ids and indices[node['parent']] < index,
                    'Missing or late parent')
            children[node['parent']].append(node['id'])
    require(len(roots) == 1, 'Not exactly one root')
    normalized, order = [], []

    def visit(node_id, path, parent, child_index):
        node = ids[node_id]
        order.append(node_id)
        record = {'path': path, 'parentPath': parent, 'ordinal': len(normalized),
                  'childIndex': child_index, 'childCount': len(children[node_id]),
                  'tag': node['tag'], 'role': node['role']}
        for key in ('text', 'href'):
            if key in node:
                record[key] = node[key]
        if node['role'] == 'text':
            units = len(node['text'].encode('utf-16-le')) // 2
            require(node['textTruncated'] is False and node['textRange'] == [0, units]
                    and units <= 1024, 'Truncated or oversized successful text')
        normalized.append(record)
        for index, child in enumerate(children[node_id]):
            visit(child, path + '/' + str(index), path, index)

    visit(roots[0], '0', '', 0)
    require(order == [node['id'] for node in nodes], 'IPC is not a complete valid preorder')
    return normalized


def resolve_recorded_path(value):
    expanded = os.path.expandvars(str(value))
    require(not re.search(r"\$\{XOS_[A-Z0-9_]+\}", expanded), "Set the XOS path variables before verifying inputs")
    return Path(expanded)


def verify_input_versions(report, source_root):
    versions = {}
    for name, entry in report['inputs'].items():
        path = resolve_recorded_path(entry['path'])
        if path.is_file() and sha(path.read_bytes()) == entry['sha256']:
            versions[name] = 'MATCH_CURRENT_FILE'
            continue
        # Later harness-only fixes do not retroactively alter a captured run.
        # Resolve an old clean checkout's exact source blob when it is recorded.
        checkout = report.get('source_checkout', {})
        head = checkout.get('head', '')
        relative = None
        try:
            relative = path.relative_to(source_root)
        except ValueError:
            pass
        if relative and re.fullmatch(r'[0-9a-f]{40}', head) and not checkout.get('tracked_changes'):
            result = subprocess.run(['git', 'show', head + ':' + relative.as_posix()],
                                    cwd=source_root, capture_output=True)
            if result.returncode == 0 and sha(result.stdout) == entry['sha256']:
                versions[name] = 'MATCH_RECORDED_CLEAN_GIT_BLOB:' + head
                continue
        require(False, 'Cannot verify recorded input: ' + name)
    return versions


def common(folder, source_root, expected_client_exit):
    report = json.loads((folder / 'report.json').read_bytes())
    serial = (folder / 'serial.log').read_bytes()
    require(sha(serial) == report['serial_sha256'], 'Serial digest mismatch')
    records = records_from_serial(serial)
    for entry in report['frames'] + report['oracles']:
        record = records[(entry['direction'], entry['sequence'])]
        payload = record['payload']
        require(payload == (folder / entry['file']).read_bytes() and
                sha(payload) == entry['sha256'] and len(payload) == entry['bytes'],
                'Serial/exported payload mismatch')
        require((entry['begin'], entry['end']) == (record['begin'], record['end']),
                'Reported serial offsets differ')
        if 'wire_file' in entry:
            wire = (folder / entry['wire_file']).read_bytes()
            expected = struct.pack('<4sII', b'SSG1', len(payload), entry['sequence']) + payload
            require(wire == expected and sha(wire) == entry['wire_sha256'],
                    'Reconstructed wire mismatch')
    require(len(records) == len(report['frames']) + len(report['oracles']), 'Unreported serial records')
    before = records[('ORACLE', 1)]['data']
    require(before['phase'] == 'before' and before['status'] == 'OK', 'Unsuccessful before Oracle')
    require(before['nodeCount'] == len(before['nodes']) and
            before['structureSha256'] == digest_nodes(before['nodes']), 'Oracle count/digest mismatch')
    require(sha((folder / 'input.html').read_bytes()) == before['inputSha256'] ==
            report['inputs']['input']['sha256'], 'Actual imported input mismatch')
    versions = verify_input_versions(report, source_root)
    receipt = json.loads((folder / 'browser.receipt.json').read_bytes())
    require(receipt['test_structure_oracle'] is True and
            receipt['elf_sha256'] == report['inputs']['browser']['sha256'], 'Browser receipt mismatch')
    for path, expected in receipt['inputs'].items():
        require(sha(resolve_recorded_path(path).read_bytes()) == expected, 'Changed Browser build input: ' + path)
    counters = [list(map(int, row)) for row in re.findall(
        rb'\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)', serial)]
    require(counters == [report['baseline'], report['display'], report['after']] and
            counters[1] == counters[2], 'Resources not recovered to display baseline')
    identities = re.findall(rb'SSG_SESSION parent=(\d+) provider=(\d+) consumer=(\d+) instance=([0-9a-f]{32}) text_scope=explicit', serial)
    require(len(identities) == 1, 'Ambiguous process identities')
    parent, provider, consumer = map(int, identities[0][:3])
    require(len({parent, provider, consumer}) == 3 and before['providerPid'] == str(provider)
            and before['sourceInstance'] == identities[0][3].decode(), 'Process/Oracle binding mismatch')
    for child, code in (('consumer', expected_client_exit), ('provider', 0)):
        observed = re.findall(('SSG_SESSION ' + child + r'_wait=(-?\d+) outcome=(\d+) code=(-?\d+)').encode(), serial)
        require(observed == [(b'0', b'1', str(code).encode())], 'Unexpected child outcome')
    count = len([key for key in records if key[0] == 'RESP'])
    require(len([key for key in records if key[0] == 'REQ']) == count and count > 0,
            'Unpaired IPC records')
    requests = [records[('REQ', i)]['data'] for i in range(1, count + 1)]
    pages = [records[('RESP', i)]['data'] for i in range(1, count + 1)]
    require(requests[0] == {'op': 'snapshot_begin', 'maxNodes': 8}, 'Unexpected request scope')
    for index, page in enumerate(pages):
        require(page['sourceInstance'] == before['sourceInstance'] and
                page['providerPid'] == before['providerPid'], 'IPC source mismatch')
        require(records[('REQ', index + 1)]['end'] <= records[('RESP', index + 1)]['begin'],
                'Response recorded before request')
        if index:
            require(requests[index] == {'op': 'snapshot_next', 'cursor': pages[index - 1]['cursor'],
                                       'sourceInstance': before['sourceInstance']}, 'Broken cursor chain')
    require(records[('REQ', 1)]['end'] <= records[('ORACLE', 1)]['begin'] <
            records[('ORACLE', 1)]['end'] <= records[('RESP', 1)]['begin'], 'Before Oracle order mismatch')
    context = {'run': folder.name, 'input_bytes': (folder / 'input.html').stat().st_size,
               'input_sha256': before['inputSha256'], 'parent_pid': parent,
               'provider_pid': provider, 'consumer_pid': consumer, 'resources': counters,
               'input_version_checks': versions, 'browser_receipt_inputs_checked': len(receipt['inputs'])}
    return report, serial, records, before, pages, context


def audit_geometry(folder, report, serial, records, originals):
    geometry = report['geometry']
    if geometry['status'] != 'PASSED_SCOPED':
        return {'status': 'NOT_RUN', 'scope': 'No link qualification reported for this capture'}
    from PIL import Image
    with Image.open(folder / 'link-before.png') as picture:
        width, height = picture.size
    if 'screen_size' in geometry:
        require(geometry['screen_size'] == [width, height], 'Reported screen size differs from actual PNG')
    selected = next(node for node in originals if node['id'] == geometry['consumer_node_id'])
    require(selected == geometry['node'] and selected['href'] == geometry['href'], 'Geometry node differs from IPC')
    px, py = geometry['screen_point']
    require(0 <= px < width and 0 <= py < height, 'Point outside actual screenshot')
    ox, oy = geometry['window_origin']
    require(any(x + ox <= px < x + ox + w and y + oy <= py < y + oy + h
                for x, y, w, h in selected['visibleFragments']), 'Point outside IPC visible fragment')
    events = json.loads((folder / 'qmp-events.json').read_bytes())
    low, high = [0, 0], [width - 1, height - 1]
    buttons = []
    for record in events:
        require(record.get('returned') == {}, 'QMP event did not complete successfully')
        if record['command'] != 'input-send-event':
            continue
        require(record['serial_offset'] >= records[('RESP', len([k for k in records if k[0] == 'RESP']))]['end'],
                'Geometry input occurred before terminal page receipt')
        for event in record['arguments']['events']:
            if event['type'] == 'rel':
                axis = 0 if event['data']['axis'] == 'x' else 1
                maximum = (width, height)[axis] - 1
                for position in (low, high):
                    position[axis] = max(0, min(maximum, position[axis] + event['data']['value']))
            if event['type'] == 'btn':
                require(event['data']['button'] == 'left' and low == high == [px, py],
                        'Relative motion does not converge to claimed click point')
                buttons.append(event['data']['down'])
    require(buttons == [True, False], 'Expected exactly one physical click')
    target = geometry['loaded_target']
    require(re.findall(rb'^BROWSER_LINK target=([^\r\n]+)', serial, re.M) == [target.encode()],
            'Unexpected actual link callback target')
    require(('BROWSER_LOADED path=' + target + ' ').encode() in serial,
            'Actual target document not loaded')
    # This one fixture's resolved target is unique, avoiding fragment aliases.
    target_basename = target.rsplit('/', 1)[-1]
    require(sum(node.get('href', '').split('#', 1)[0] == target_basename for node in originals) == 1,
            'Multiple document links share the observed target')
    return {'status': 'PASSED_SCOPED', 'scope': 'One recorded link click after paging only',
            'node_id': selected['id'], 'href': selected['href'], 'point': [px, py],
            'actual_screenshot_size': [width, height], 'qmp_records': len(events),
            'reported_screen_size': geometry.get('screen_size'),
            'global_geometry': 'NOT_QUALIFIED', 'during_paging_interaction': 'NOT_TESTED'}


def audit_positive(folder, source_root):
    report, serial, records, before, pages, result = common(folder, source_root, 0)
    require(len([key for key in records if key[0] == 'ORACLE']) == 2, 'Wrong Oracle count')
    after = records[('ORACLE', 2)]['data']
    require(after['phase'] == 'after' and {k: v for k, v in before.items() if k != 'phase'} ==
            {k: v for k, v in after.items() if k != 'phase'}, 'Before/after model or metadata differs')
    originals = []
    for index, page in enumerate(pages):
        complete = index == len(pages) - 1
        require(page['status'] == 'OK' and page['pageSequence'] == str(index + 1) and
                page['complete'] is complete and page['traversalComplete'] is complete,
                'Invalid success/end sequence')
        require(page['hasData'] is bool(page['nodes']) and page['hasNext'] is (not complete),
                'Invalid page flags')
        require(page['visited'] == len(page['nodes']) <= 8, 'Invalid page visit/output counts')
        for field in ('sourceEpoch', 'sourceRevision'):
            require(page[field] == before[field], 'Page document revision differs')
        originals.extend(page['nodes'])
    require(pages[-1]['cursor'] == '', 'Terminal page retains cursor')
    normalized = adjacency_reconstruction(originals)
    require(normalized == before['nodes'] == after['nodes'], 'Full node dictionary comparison failed')
    digest = digest_nodes(normalized)
    require(digest == before['structureSha256'], 'Independently recomputed digest differs')
    comparison = json.loads((folder / 'structure-comparison.json').read_bytes())
    require(comparison['node_count'] == len(normalized) and comparison['structure_sha256'] == digest,
            'Main comparison summary differs')
    require(len(comparison['comparison']) == len(normalized), 'Comparison rows missing')
    for index, row in enumerate(comparison['comparison']):
        require({k: v for k, v in row.items() if k not in ('status', 'consumerId', 'consumerParent')}
                == normalized[index] and row['status'] == 'MATCH' and
                row['consumerId'] == originals[index]['id'] and
                row['consumerParent'] == originals[index]['parent'], 'Main comparison row differs')
    done = re.findall(rb'SSG_PAGED_CONSUMER_DONE pages=(\d+) nodes=(\d+) complete=(\d+) completeness=ORACLE_REQUIRED', serial)
    require(done == [(str(len(pages)).encode(), str(len(normalized)).encode(), b'1')], 'Consumer summary differs')
    result.update(status='PASSED_SCOPED', qualification='INDEPENDENT_AUDIT_OF_RECORDED_A1',
                  node_count=len(normalized), page_count=len(pages),
                  page_sizes=[len(page['nodes']) for page in pages], structure_sha256=digest,
                  roles={role: sum(node['role'] == role for node in normalized)
                         for role in ('element', 'text', 'link')},
                  link_hit=audit_geometry(folder, report, serial, records, originals),
                  gate_A_overall='NOT_QUALIFIED', gate_B='NOT_RUN', gate_C='NOT_RUN',
                  performance='NOT_QUALIFIED')
    return result


def audit_negative(folder, source_root):
    report, serial, records, before, pages, result = common(folder, source_root, 1)
    require(len([key for key in records if key[0] == 'ORACLE']) == 1, 'Unexpected completed Oracle')
    require(pages[-1]['status'] == 'RESOURCE_LIMIT' and 'nodes' not in pages[-1] and
            'complete' not in pages[-1], 'Expected explicit resource failure without partial success')
    oversized = [{'path': node['path'], 'ordinal': node['ordinal'],
                  'utf16_units': len(node['text'].encode('utf-16-le')) // 2}
                 for node in before['nodes'] if node['role'] == 'text' and
                 len(node['text'].encode('utf-16-le')) // 2 > 1024]
    require(oversized, 'Oracle did not observe an oversized text node')
    prefix = []
    for page in pages[:-1]:
        require(page['status'] == 'OK' and page['complete'] is False, 'Early failure/completion')
        prefix.extend(page['nodes'])
    normalized = adjacency_reconstruction(prefix)
    for reference, node in zip(before['nodes'], normalized):
        require(set(reference) == set(node), 'Prefix fields differ')
        for key in node:
            require(node[key] <= reference[key] if key == 'childCount' else node[key] == reference[key],
                    'Prefix differs from independent Oracle')
    require(len(normalized) <= oversized[0]['ordinal'] < len(normalized) + 8,
            'First oversized text not within rejected page budget')
    done = re.findall(rb'SSG_PAGED_CONSUMER_DONE pages=(\d+) nodes=(\d+) complete=(\d+) completeness=ORACLE_REQUIRED', serial)
    require(done == [(str(len(pages)).encode(), str(len(normalized)).encode(), b'0')], 'Consumer accepted incomplete result')
    result.update(status='PASSED_SCOPED', qualification='INDEPENDENT_AUDIT_OF_RECORDED_RESOURCE_REJECTION',
                  oracle_node_count=before['nodeCount'], oversized_text_nodes=oversized,
                  received_nodes=len(normalized), final_response='RESOURCE_LIMIT',
                  structure_completeness='NOT_QUALIFIED', gate_A_overall='NOT_QUALIFIED')
    return result


def audit_boot_failure(folder):
    report = json.loads((folder / 'report.json').read_bytes())
    require(report['status'] == 'FAILED' and (folder / 'serial.log').read_bytes() == b'',
            'First attempt is no longer preserved as a no-guest-output failure')
    error = (folder / 'qemu_qemu.log').read_text()
    require('Failed to bind socket' in error and 'Operation not permitted' in error,
            'First attempt blocker differs from reported QMP bind denial')
    return {'run': folder.name, 'status': 'FAILED_ATTEMPT_PRESERVED',
            'guest_boot_observed': False, 'serial_bytes': 0, 'qemu_error': error.strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument('--positive', nargs='+', default=['p2d-oracle-02', 'p2f-oracle-01'])
    parser.add_argument('--negative', default='text-limit-01')
    parser.add_argument('--boot-failure', default='p2d-oracle-01')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = [audit_positive(args.runs_root / name, args.source_root.resolve()) for name in args.positive]
    results.append(audit_negative(args.runs_root / args.negative, args.source_root.resolve()))
    results.append(audit_boot_failure(args.runs_root / args.boot_failure))
    document = {'audit_kind': 'Independent read-only audit of previously recorded real guest captures',
                'not_a_new_guest_run': True, 'does_not_parse_source_HTML_to_generate_answers': True,
                'production_validator_imported': False,
                'auditor_script_sha256': sha(Path(__file__).read_bytes()),
                'runs_root': str(args.runs_root.resolve()), 'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    public = portable(document, [('XOS_TEST_OUT', args.runs_root)], strict=True)
    args.output.write_text(json.dumps(public, indent=2, ensure_ascii=False) + '\n')
    for row in results:
        print(row['run'], row['status'], row.get('node_count', row.get('oracle_node_count', '')))


if __name__ == '__main__':
    main()
