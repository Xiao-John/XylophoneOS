#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strict Gate A1 comparison of guest liteHTML oracles and Consumer IPC logs.

This module does not parse HTML or invent an expected DOM.  The reference is
the separately enumerated, bounded liteHTML document in the *same guest* before
and after paging.  Passing establishes structure and text only for that capture;
rendering completeness, compositor visibility, Diff and recovery remain separate.
"""
import base64
import hashlib
import json
import re

SCHEMA = 'xos-litehtml-structure-oracle-v1'
CANONICAL_FORMAT = 'netstring-utf8-v1'
MAX_NODES = 4096
MAX_ORACLE_BYTES = 1024 * 1024
MAX_PAGES = 1024
_DECIMAL = re.compile(r'(?:0|[1-9][0-9]*)\Z')
_POSITIVE = re.compile(r'[1-9][0-9]*\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_INSTANCE = re.compile(r'[0-9a-f]{32}\Z')
_PATH = re.compile(r'0(?:/(?:0|[1-9][0-9]*))*\Z')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _string(value, name, pattern=None):
    _require(type(value) is str, name + ' must be a string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError(name + ' contains an invalid Unicode scalar') from error
    if pattern:
        _require(pattern.fullmatch(value), name + ' has invalid syntax')
    return value


def _integer(value, name, minimum=0, maximum=None):
    _require(type(value) is int and value >= minimum and
             (maximum is None or value <= maximum), name + ' is out of range')
    return value


def canonical_bytes(nodes):
    """Cross-language digest format; lengths count UTF-8 bytes, not characters.

    Each record contains eleven netstrings in the documented order. Presence
    fields distinguish a missing text/href from a present empty string. A newline
    separates records, and the fixed prefix versions the interpretation.
    """
    result = bytearray(b'XOS-LITEHTML-STRUCTURE-V1\n')
    for node in nodes:
        fields = [node['path'], node['parentPath'], str(node['ordinal']),
                  str(node['childIndex']), str(node['childCount']), node['tag'],
                  node['role'], '1' if 'text' in node else '0', node.get('text', ''),
                  '1' if 'href' in node else '0', node.get('href', '')]
        for field in fields:
            data = _string(field, 'canonical field').encode('utf-8')
            result += str(len(data)).encode('ascii') + b':' + data + b','
        result += b'\n'
    return bytes(result)


def structure_digest(nodes):
    return hashlib.sha256(canonical_bytes(nodes)).hexdigest()


def _json_object(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate JSON object key: ' + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('non-finite JSON number: ' + value)

    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs,
                           parse_constant=nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError('invalid captured JSON: ' + str(error)) from error
    _require(type(value) is dict, 'captured JSON is not an object')
    return value


def decode_capture(serial):
    """Decode complete, ordered log records; return raw payloads and JSON.

    Returns {'frames': [...], 'oracles': [...]}. Each entry has payload (bytes),
    data (dict), begin/end byte offsets, sequence and SHA-256. Frame entries also
    carry direction. Oracles use sequence as the capture ID. Orphan, duplicate,
    truncated, out-of-order and malformed record parts are rejected.
    """
    _require(type(serial) is bytes, 'serial capture must be bytes')
    pending, seen = {}, set()
    frames, oracles = [], []
    offset = 0
    patterns = {
        'frame_begin': re.compile(rb'SSG_FRAME_BEGIN (REQ|RESP) ([1-9][0-9]*) ([1-9][0-9]*) ([1-9][0-9]*)'),
        'frame_part': re.compile(rb'SSG_FRAME_PART (REQ|RESP) ([1-9][0-9]*) ([0-9]+) ([A-Za-z0-9+/=]+)'),
        'frame_end': re.compile(rb'SSG_FRAME_END (REQ|RESP) ([1-9][0-9]*)'),
        'oracle_begin': re.compile(rb'SSG_ORACLE_BEGIN ([1-9][0-9]*) ([1-9][0-9]*) ([1-9][0-9]*)'),
        'oracle_part': re.compile(rb'SSG_ORACLE_PART ([1-9][0-9]*) ([0-9]+) ([A-Za-z0-9+/=]+)'),
        'oracle_end': re.compile(rb'SSG_ORACLE_END ([1-9][0-9]*)'),
    }
    for raw_line in serial.splitlines(keepends=True):
        line = raw_line.rstrip(b'\r\n')
        if b'SSG_FRAME_' not in line and b'SSG_ORACLE_' not in line:
            offset += len(raw_line)
            continue
        matched = None
        for name, pattern in patterns.items():
            match = pattern.fullmatch(line)
            if match:
                matched = (name, list(match.groups()))
                break
        _require(matched is not None, 'malformed frame/oracle log record')
        name, groups = matched
        is_frame = name.startswith('frame_')
        direction = groups.pop(0).decode('ascii') if is_frame else 'ORACLE'
        sequence = int(groups.pop(0))
        key = (direction, sequence)
        if name.endswith('_begin'):
            _require(key not in seen, 'duplicate captured record header: ' + str(key))
            _require(len(seen) < 2 * MAX_PAGES + 2, 'too many captured records')
            length, encoded_length = map(int, groups)
            maximum = (4096 if direction == 'REQ' else 81920) if is_frame else MAX_ORACLE_BYTES
            _require(length <= maximum, 'captured record exceeds protocol/test budget')
            _require(encoded_length == 4 * ((length + 2) // 3), 'invalid advertised base64 length')
            pending[key] = {'direction': direction, 'sequence': sequence,
                            'bytes': length, 'encoded_bytes': encoded_length,
                            'begin': offset, 'chunks': bytearray()}
            seen.add(key)
        elif name.endswith('_part'):
            _require(key in pending, 'orphan/late captured record part: ' + str(key))
            entry = pending[key]
            part_offset, chunk = int(groups[0]), groups[1]
            _require(part_offset == len(entry['chunks']), 'duplicate or non-contiguous captured parts')
            _require(len(entry['chunks']) + len(chunk) <= entry['encoded_bytes'], 'captured parts exceed declared length')
            entry['chunks'] += chunk
        else:
            _require(key in pending, 'orphan/duplicate captured record end: ' + str(key))
            entry = pending.pop(key)
            encoded = bytes(entry.pop('chunks'))
            _require(len(encoded) == entry['encoded_bytes'], 'truncated captured record')
            try:
                payload = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as error:
                raise ValueError('invalid captured base64') from error
            _require(len(payload) == entry['bytes'] and base64.b64encode(payload) == encoded,
                     'captured payload length/encoding mismatch')
            entry.update(payload=payload, data=_json_object(payload),
                         sha256=hashlib.sha256(payload).hexdigest(), end=offset + len(raw_line))
            (frames if is_frame else oracles).append(entry)
        offset += len(raw_line)
    _require(not pending, 'unterminated captured record: ' + str(list(pending)))
    return {'frames': frames, 'oracles': oracles}


def validate_oracle(oracle, input_sha256, phase):
    _require(oracle.get('schema') == SCHEMA and oracle.get('status') == 'OK',
             'missing or unsuccessful independent liteHTML oracle')
    _require(oracle.get('phase') == phase, 'unexpected oracle phase')
    _require(oracle.get('document') == '/web/ssg.html', 'oracle document does not match imported fixture')
    _require(oracle.get('inputSha256') == input_sha256, 'oracle input SHA-256 does not match imported bytes')
    _string(oracle.get('sourceInstance'), 'oracle sourceInstance', _INSTANCE)
    for field in ('providerPid', 'sourceEpoch', 'sourceRevision'):
        _string(oracle.get(field), 'oracle ' + field, _POSITIVE)
    nodes = oracle.get('nodes')
    _require(type(nodes) is list, 'oracle nodes must be an array')
    _integer(oracle.get('nodeCount'), 'oracle nodeCount', 1, MAX_NODES)
    _require(len(nodes) == oracle['nodeCount'], 'oracle nodeCount disagrees with records')
    by_path, children, ancestors = {}, {}, []
    payload_bytes = 0
    for ordinal, node in enumerate(nodes):
        _require(type(node) is dict, 'oracle node must be an object')
        path = _string(node.get('path'), 'oracle path', _PATH)
        parent = _string(node.get('parentPath'), 'oracle parentPath')
        _require(path not in by_path and path.count('/') <= 32, 'duplicate/deep oracle path')
        _require(type(node.get('ordinal')) is int and node['ordinal'] == ordinal, 'oracle preorder ordinal mismatch')
        index = _integer(node.get('childIndex'), 'oracle childIndex', 0, MAX_NODES)
        _integer(node.get('childCount'), 'oracle childCount', 0, MAX_NODES)
        _string(node.get('tag'), 'oracle tag')
        role = _string(node.get('role'), 'oracle role')
        _require(role in ('text', 'link', 'element'), 'unknown oracle role')
        expected_keys = {'path', 'parentPath', 'ordinal', 'childIndex', 'childCount', 'tag', 'role'}
        if role == 'text':
            expected_keys.add('text')
        if role == 'link':
            expected_keys.add('href')
        _require(set(node) == expected_keys, 'oracle node fields do not match its role')
        for field in ('text', 'href'):
            if field in node:
                payload_bytes += len(_string(node[field], 'oracle ' + field).encode('utf-8'))
        if ordinal == 0:
            _require(path == '0' and parent == '' and index == 0, 'oracle root is incorrect')
        else:
            _require(parent in ancestors, 'oracle parent is absent or subtree already closed')
            ancestors = ancestors[:ancestors.index(parent) + 1]
            expected_index = children[parent]
            _require(index == expected_index and path == parent + '/' + str(expected_index),
                     'oracle sibling order/path mismatch')
            children[parent] += 1
        by_path[path] = node
        children[path] = 0
        ancestors.append(path)
    _require(payload_bytes <= 256 * 1024, 'oracle text/href exceeds independent test budget')
    for path, count in children.items():
        _require(by_path[path]['childCount'] == count, 'oracle childCount mismatch at ' + path)
    _require(oracle.get('canonicalFormat') == CANONICAL_FORMAT, 'unknown oracle canonical format')
    _string(oracle.get('structureSha256'), 'oracle structureSha256', _SHA256)
    _require(oracle['structureSha256'] == structure_digest(nodes), 'oracle structure SHA-256 mismatch')
    return nodes


def normalize_consumer_nodes(nodes):
    """Reconstruct stable tree paths from ordered IPC IDs, without Oracle IDs."""
    _require(type(nodes) is list and 0 < len(nodes) <= MAX_NODES, 'Consumer node count out of test budget')
    result, mapping, ancestors, children = [], {}, [], {}
    for ordinal, node in enumerate(nodes):
        _require(type(node) is dict, 'Consumer node is not an object')
        node_id = _string(node.get('id'), 'node id', _POSITIVE)
        parent = _string(node.get('parent'), 'node parent', _DECIMAL)
        _require(node_id not in mapping, 'duplicate Consumer node ID: ' + node_id)
        if ordinal == 0:
            _require(parent == '0', 'Consumer root parent is incorrect')
            path, parent_path, index = '0', '', 0
        else:
            _require(parent != '0' and parent in mapping, 'extra root or missing Consumer parent: ' + parent)
            _require(parent in ancestors, 'Consumer revisits a closed subtree: ' + parent)
            ancestors = ancestors[:ancestors.index(parent) + 1]
            parent_path = mapping[parent]['path']
            index = children[parent]
            children[parent] += 1
            path = parent_path + '/' + str(index)
        _require(path.count('/') <= 18, 'Consumer tree exceeds Provider depth limit')
        role = _string(node.get('role'), 'Consumer role')
        tag = _string(node.get('tag'), 'Consumer tag')
        _require(role in ('text', 'link', 'element'), 'unknown Consumer role')
        _require(node.get('source') == 'litehtml-model-and-render-layout', 'unexpected Consumer node source')
        _require(node.get('contentTrust') == 'untrusted-document-content' and
                 node.get('actionAuthority') == 'READ_ONLY_NO_GRANT', 'Consumer node authority/trust mismatch')
        normalized = {'path': path, 'parentPath': parent_path, 'ordinal': ordinal,
                      'childIndex': index, 'childCount': 0, 'tag': tag, 'role': role}
        if role == 'text':
            text = _string(node.get('text'), 'Consumer text')
            units = len(text.encode('utf-16-le')) // 2
            _require(units <= 1024 and node.get('textTruncated') is False,
                     'Consumer text truncated or exceeds Provider limit')
            text_range = node.get('textRange')
            _require(type(text_range) is list and len(text_range) == 2 and
                     all(type(x) is int for x in text_range) and text_range == [0, units],
                     'Consumer textRange does not cover the exact text')
            normalized['text'] = text
        else:
            _require('text' not in node, 'unexpected text on a non-text Consumer node')
        if role == 'link':
            normalized['href'] = _string(node.get('href'), 'Consumer href')
        else:
            _require('href' not in node, 'unexpected href on a non-link Consumer node')
        mapping[node_id] = normalized
        children[node_id] = 0
        ancestors.append(node_id)
        result.append(normalized)
    for node_id, count in children.items():
        mapping[node_id]['childCount'] = count
    return result


def compare_structure(reference, nodes):
    actual = normalize_consumer_nodes(nodes)
    _require(len(actual) == len(reference),
             'structure node count differs: oracle=%d Consumer=%d' % (len(reference), len(actual)))
    for expected, observed in zip(reference, actual):
        for field in sorted(set(expected) | set(observed)):
            _require(field in expected and field in observed and expected[field] == observed[field],
                     'structure mismatch at %s field %s: oracle=%r Consumer=%r' %
                     (expected['path'], field, expected.get(field), observed.get(field)))
    return actual


def _one(serial, pattern, name):
    matches = list(re.finditer(pattern, serial, re.MULTILINE))
    _require(len(matches) == 1, 'expected exactly one ' + name + ' record')
    return matches[0]


def validate_capture(serial, input_sha256):
    """Return a JSON-serializable scoped A1 report or raise ValueError.

    This requires complete Consumer logs *and* successful child exit records.
    The caller separately verifies input executable hashes and resource recovery.
    """
    _string(input_sha256, 'expected input SHA-256', _SHA256)
    capture = decode_capture(serial)
    frames, oracles = capture['frames'], capture['oracles']
    _require(len(oracles) == 2 and [x['sequence'] for x in oracles] == [1, 2],
             'expected exactly two ordered independent Oracle captures')
    before, after = [x['data'] for x in oracles]
    reference = validate_oracle(before, input_sha256, 'before')
    validate_oracle(after, input_sha256, 'after')
    for field in ('document', 'inputSha256', 'sourceInstance', 'providerPid',
                  'sourceEpoch', 'sourceRevision', 'nodeCount', 'structureSha256', 'nodes'):
        _require(before[field] == after[field], 'Oracle source/model changed during paging: ' + field)
    requests = [x for x in frames if x['direction'] == 'REQ']
    responses = [x for x in frames if x['direction'] == 'RESP']
    pages = len(requests)
    _require(1 <= pages <= MAX_PAGES and len(responses) == pages, 'unpaired or missing IPC request/response')
    _require([x['sequence'] for x in requests] == list(range(1, pages + 1)) and
             [x['sequence'] for x in responses] == list(range(1, pages + 1)),
             'IPC message sequence is not contiguous')
    _require(requests[0]['end'] <= oracles[0]['begin'] < oracles[0]['end'] <= responses[0]['begin'],
             'before Oracle does not precede the first received response')
    _require(requests[-1]['end'] <= oracles[1]['begin'] < oracles[1]['end'] <= responses[-1]['begin'] and
             oracles[0]['end'] <= oracles[1]['begin'],
             'after Oracle is not bound to the terminal page')
    first_request = requests[0]['data']
    _require(first_request.get('op') == 'snapshot_begin' and
             set(first_request) <= {'op', 'maxNodes', 'role', 'visibleOnly'}, 'invalid full-tree begin request')
    limit = _integer(first_request.get('maxNodes', 16), 'requested page node limit', 1, 16)
    _require(first_request.get('role', '') == '' and first_request.get('visibleOnly', False) is False,
             'Gate A1 requires an unfiltered full-tree query')
    all_nodes, page_counts, seen_cursors = [], [], set()
    previous_cursor, scroll_y = None, None
    for i, (request_record, response_record) in enumerate(zip(requests, responses), 1):
        _require(request_record['end'] <= response_record['begin'], 'response precedes completed request log')
        if i > 1:
            _require(responses[i - 2]['end'] <= request_record['begin'], 'overlapping IPC message sequence')
            request = request_record['data']
            _require(request == {'op': 'snapshot_next', 'sourceInstance': before['sourceInstance'],
                                 'cursor': previous_cursor}, 'continuation request/source/cursor mismatch')
        response = response_record['data']
        _require(response.get('status') == 'OK', 'Provider page status is not OK: ' + str(response.get('status')))
        for field in ('sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision'):
            _require(type(response.get(field)) is str and response[field] == before[field],
                     'IPC source differs from independent Oracle: ' + field)
        _require(response.get('sourceValid') is True and response.get('query') == '' and
                 response.get('visibleOnly') is False, 'invalid/stale/filtered page scope')
        _require(response.get('pageSequence') == str(i), 'page sequence mismatch')
        nodes = response.get('nodes')
        _require(type(nodes) is list and len(nodes) <= limit, 'page nodes exceed requested limit')
        complete = response.get('complete')
        _require(type(complete) is bool and complete == (i == pages), 'missing or premature traversal completion')
        _require(response.get('traversalComplete') is complete and response.get('hasNext') is (not complete) and
                 response.get('hasData') is bool(nodes), 'inconsistent page completion flags')
        _require(response.get('stopReason') == ('EXHAUSTED' if complete else 'PAGE_BUDGET'), 'invalid page stop reason')
        _require(response.get('baselineStatus') == ('CONSUMER_MUST_VALIDATE' if complete else 'INCOMPLETE') and
                 response.get('diffStatus') == 'RESET_REQUIRED_NO_PAGED_BASELINE', 'unexpected baseline/Diff qualification')
        visited = _integer(response.get('visited'), 'visited node count', 0, 16)
        _require(visited == len(nodes), 'unfiltered page visit/output count mismatch')
        _require(complete or nodes, 'empty incomplete full-tree page does not demonstrate progress')
        _string(response.get('elapsedMs'), 'elapsedMs', _DECIMAL)
        y = _integer(response.get('scrollY'), 'scrollY', 0, 65536)
        if scroll_y is None:
            scroll_y = y
        _require(y == scroll_y, 'scroll state changed during fixed-history capture')
        cursor = _string(response.get('cursor'), 'page cursor')
        if complete:
            _require(cursor == '', 'completed page retains a continuation cursor')
        else:
            _require(cursor and cursor not in seen_cursors, 'missing or reused continuation cursor')
            seen_cursors.add(cursor)
        previous_cursor = cursor
        page_counts.append(len(nodes))
        all_nodes.extend(nodes)
        _require(len(all_nodes) <= MAX_NODES, 'Consumer aggregate exceeds test node budget')
    normalized = compare_structure(reference, all_nodes)
    identity = _one(serial, rb'^SSG_SESSION parent=([1-9][0-9]*) provider=([1-9][0-9]*) consumer=([1-9][0-9]*) instance=([0-9a-f]{32}) text_scope=explicit\r?$', 'authorized session identity')
    parent_pid, provider_pid, consumer_pid = [int(x) for x in identity.groups()[:3]]
    _require(len({parent_pid, provider_pid, consumer_pid}) == 3, 'session does not establish three independent processes')
    _require(str(provider_pid) == before['providerPid'] and identity[4].decode() == before['sourceInstance'],
             'session identity disagrees with Oracle and IPC')
    ready = _one(serial, rb'^SSG_PROVIDER_READY pid=([1-9][0-9]*) instance=([0-9a-f]{32}) text=1 kind=browser\r?$', 'authorized Browser provider')
    _require(int(ready[1]) == provider_pid and ready[2] == identity[4], 'provider identity/scope mismatch')
    consumer = _one(serial, rb'^SSG_CONSUMER_START pid=([1-9][0-9]*)\r?$', 'Consumer process start')
    _require(int(consumer[1]) == consumer_pid, 'Consumer process identity mismatch')
    done = _one(serial, rb'^SSG_PAGED_CONSUMER_DONE pages=([0-9]+) nodes=([0-9]+) complete=([01]) completeness=ORACLE_REQUIRED\r?$', 'Consumer completion')
    _require(tuple(map(int, done.groups())) == (pages, len(normalized), 1), 'Consumer did not accept the complete matching tree')
    _require(done.start() >= responses[-1]['end'], 'Consumer completion precedes terminal response')
    for child in ('consumer', 'provider'):
        waited = _one(serial, rb'^SSG_SESSION ' + child.encode() + rb'_wait=(-?[0-9]+) outcome=([0-9]+) code=(-?[0-9]+)\r?$', child + ' exit')
        _require(tuple(map(int, waited.groups())) == (0, 1, 0) and waited.start() > done.start(),
                 child + ' did not exit successfully after comparison capture')
    _require(b'SSG_CONSUMER_TRANSPORT ' not in serial, 'Consumer recorded a transport error')
    geometry_incomplete = sum(n.get('fragmentsComplete') is False for n in all_nodes)
    geometry_unknown = sum(type(n.get('fragmentsComplete')) is not bool for n in all_nodes)
    return {
        'status': 'PASSED_SCOPED', 'qualification': 'A1_STRUCTURE_AND_TEXT',
        'scope': 'one fixed loaded liteHTML document; unfiltered full tree; guest IPC capture',
        'node_count': len(normalized), 'page_node_counts': page_counts,
        'structure_sha256': structure_digest(normalized), 'canonical_format': CANONICAL_FORMAT,
        'input_sha256': input_sha256,
        'processes': {'parent_pid': parent_pid, 'provider_pid': provider_pid,
                      'consumer_pid': consumer_pid, 'source_instance': before['sourceInstance'],
                      'source_epoch': before['sourceEpoch'], 'source_revision': before['sourceRevision']},
        'checks': ['independent_before_after_oracles_agree', 'input_and_source_bound',
                   'strict_complete_IPC_frames', 'contiguous_single_use_continuation',
                   'all_expected_nodes_no_extra_or_duplicate', 'unique_root',
                   'parents_precede_children', 'parent_relationships_and_sibling_order',
                   'exact_roles_tags_text_and_href', 'independent_terminal_count',
                   'Consumer_completion_and_both_child_exits'],
        'comparison': [{'status': 'MATCH', 'consumerId': node['id'], 'consumerParent': node['parent'],
                        **normalized[i]} for i, node in enumerate(all_nodes)],
        'oracles': [{k: record[k] for k in ('sequence', 'bytes', 'sha256')}
                    | {'phase': record['data']['phase']} for record in oracles],
        'frames': [{k: record[k] for k in ('direction', 'sequence', 'bytes', 'sha256')} for record in frames],
        'rendered_fragments': {'status': 'NOT_QUALIFIED',
                               'provider_claimed_incomplete_nodes': geometry_incomplete,
                               'nodes_without_boolean_completeness': geometry_unknown},
        'viewport_visibility': 'NOT_QUALIFIED', 'screen_occlusion': 'NOT_TESTED',
        'gate_A_overall': 'NOT_QUALIFIED', 'gate_B': 'NOT_RUN', 'gate_C': 'NOT_RUN',
    }


def validate_resource_rejection(serial, input_sha256):
    """Qualify an observed text-limit rejection, never structure completeness.

    The complete before Oracle must contain a text node above 1024 UTF-16 units.
    Earlier successful pages must be an exact prefix of that tree. Every logged
    request, response, source and child outcome is checked; a generic process or
    transport failure cannot substitute for an explicit Provider RESOURCE_LIMIT.
    No after Oracle is expected because the traversal did not complete.
    """
    _string(input_sha256, 'expected input SHA-256', _SHA256)
    capture = decode_capture(serial)
    frames, oracles = capture['frames'], capture['oracles']
    _require(len(oracles) == 1 and oracles[0]['sequence'] == 1,
             'resource rejection requires exactly one before Oracle')
    before = oracles[0]['data']
    reference = validate_oracle(before, input_sha256, 'before')
    oversized = [{'path': node['path'], 'ordinal': node['ordinal'],
                  'utf16_units': len(node['text'].encode('utf-16-le')) // 2}
                 for node in reference if node['role'] == 'text' and
                 len(node['text'].encode('utf-16-le')) // 2 > 1024]
    _require(oversized, 'Oracle contains no text beyond the documented per-node limit')
    requests = [x for x in frames if x['direction'] == 'REQ']
    responses = [x for x in frames if x['direction'] == 'RESP']
    pages = len(requests)
    _require(1 <= pages <= MAX_PAGES and len(responses) == pages,
             'unpaired or missing IPC request/response during resource rejection')
    _require([x['sequence'] for x in requests] == list(range(1, pages + 1)) and
             [x['sequence'] for x in responses] == list(range(1, pages + 1)),
             'resource rejection IPC sequence is not contiguous')
    _require(requests[0]['end'] <= oracles[0]['begin'] < oracles[0]['end'] <= responses[0]['begin'],
             'before Oracle does not precede the first received response')
    first = requests[0]['data']
    _require(first.get('op') == 'snapshot_begin' and
             set(first) <= {'op', 'maxNodes', 'role', 'visibleOnly'}, 'invalid resource-test begin request')
    limit = _integer(first.get('maxNodes', 16), 'requested page node limit', 1, 16)
    _require(first.get('role', '') == '' and first.get('visibleOnly', False) is False,
             'resource rejection test requires an unfiltered full-tree query')
    all_nodes, page_counts, seen_cursors = [], [], set()
    previous_cursor, scroll_y = None, None
    for i, (request_record, response_record) in enumerate(zip(requests, responses), 1):
        _require(request_record['end'] <= response_record['begin'], 'response precedes completed request log')
        if i > 1:
            _require(responses[i - 2]['end'] <= request_record['begin'], 'overlapping resource-test IPC messages')
            _require(request_record['data'] == {'op': 'snapshot_next', 'sourceInstance': before['sourceInstance'],
                                               'cursor': previous_cursor},
                     'resource rejection continuation request/source/cursor mismatch')
        response = response_record['data']
        for field in ('sourceInstance', 'providerPid'):
            _require(type(response.get(field)) is str and response[field] == before[field],
                     'resource rejection reply source differs from Oracle: ' + field)
        if i == pages:
            _require(response.get('status') == 'RESOURCE_LIMIT', 'terminal reply is not RESOURCE_LIMIT')
            _require(set(response) <= {'status', 'sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision'},
                     'RESOURCE_LIMIT must not contain nodes or successful-page fields')
            for field in ('sourceEpoch', 'sourceRevision'):
                if field in response:
                    _require(type(response[field]) is str and response[field] == before[field],
                             'RESOURCE_LIMIT source differs from Oracle: ' + field)
            continue
        _require(response.get('status') == 'OK', 'nonterminal reply is not a successful incomplete page')
        for field in ('sourceEpoch', 'sourceRevision'):
            _require(type(response.get(field)) is str and response[field] == before[field],
                     'resource-test page source differs from Oracle: ' + field)
        _require(response.get('sourceValid') is True and response.get('query') == '' and
                 response.get('visibleOnly') is False, 'invalid/stale/filtered resource-test scope')
        _require(response.get('pageSequence') == str(i), 'resource-test page sequence mismatch')
        nodes = response.get('nodes')
        _require(type(nodes) is list and 0 < len(nodes) <= limit, 'invalid resource-test page node count')
        _require(response.get('complete') is False and response.get('traversalComplete') is False and
                 response.get('hasNext') is True and response.get('hasData') is True and
                 response.get('stopReason') == 'PAGE_BUDGET', 'premature/inconsistent resource-test completion')
        _require(response.get('baselineStatus') == 'INCOMPLETE' and
                 response.get('diffStatus') == 'RESET_REQUIRED_NO_PAGED_BASELINE', 'unexpected resource-test baseline qualification')
        visited = _integer(response.get('visited'), 'resource-test visited count', 0, 16)
        _require(visited == len(nodes), 'resource-test visit/output count mismatch')
        _string(response.get('elapsedMs'), 'resource-test elapsedMs', _DECIMAL)
        y = _integer(response.get('scrollY'), 'resource-test scrollY', 0, 65536)
        if scroll_y is None:
            scroll_y = y
        _require(y == scroll_y, 'scroll state changed during resource-test paging')
        cursor = _string(response.get('cursor'), 'resource-test cursor')
        _require(cursor and cursor not in seen_cursors, 'missing/reused resource-test cursor')
        seen_cursors.add(cursor)
        previous_cursor = cursor
        page_counts.append(len(nodes))
        all_nodes.extend(nodes)
        _require(len(all_nodes) < len(reference), 'resource-test pages already exhausted the reference')
    normalized = normalize_consumer_nodes(all_nodes) if all_nodes else []
    # Prefix enumeration cannot know the final child counts of open ancestors.
    # Every other reference field is still exact, and observed counts cannot
    # exceed the complete Oracle counts.
    for expected, observed in zip(reference, normalized):
        _require(set(expected) == set(observed), 'resource-test prefix node fields differ from Oracle')
        for field in expected:
            if field == 'childCount':
                _require(observed[field] <= expected[field], 'resource-test prefix has extra children')
            else:
                _require(observed[field] == expected[field],
                         'resource-test prefix mismatch at %s field %s' % (expected['path'], field))
    first_oversized = oversized[0]['ordinal']
    _require(len(normalized) <= first_oversized < len(normalized) + limit,
             'first oversized text is outside the rejected page visit budget')

    # Count marker families too: a second contradictory or malformed outcome
    # must not be ignored merely because it misses a success-shaped regex.
    for prefix in (b'SSG_SESSION parent=', b'SSG_PROVIDER_READY ', b'SSG_CONSUMER_START ',
                   b'SSG_PAGED_CONSUMER_DONE ', b'SSG_SESSION consumer_wait=', b'SSG_SESSION provider_wait='):
        _require(len(re.findall(rb'^' + re.escape(prefix), serial, re.MULTILINE)) == 1,
                 'expected exactly one resource-test identity/outcome marker: ' + prefix.decode())
    identity = _one(serial, rb'^SSG_SESSION parent=([1-9][0-9]*) provider=([1-9][0-9]*) consumer=([1-9][0-9]*) instance=([0-9a-f]{32}) text_scope=explicit\r?$', 'authorized resource-test session')
    parent_pid, provider_pid, consumer_pid = [int(x) for x in identity.groups()[:3]]
    _require(len({parent_pid, provider_pid, consumer_pid}) == 3, 'resource test lacks independent session processes')
    _require(str(provider_pid) == before['providerPid'] and identity[4].decode() == before['sourceInstance'],
             'resource-test session identity differs from Oracle')
    ready = _one(serial, rb'^SSG_PROVIDER_READY pid=([1-9][0-9]*) instance=([0-9a-f]{32}) text=1 kind=browser\r?$', 'authorized resource-test Browser')
    _require(int(ready[1]) == provider_pid and ready[2] == identity[4], 'resource-test Provider identity/scope mismatch')
    consumer = _one(serial, rb'^SSG_CONSUMER_START pid=([1-9][0-9]*)\r?$', 'resource-test Consumer process')
    _require(int(consumer[1]) == consumer_pid, 'resource-test Consumer identity mismatch')
    done = _one(serial, rb'^SSG_PAGED_CONSUMER_DONE pages=([0-9]+) nodes=([0-9]+) complete=([01]) completeness=ORACLE_REQUIRED\r?$', 'resource-test Consumer result')
    _require(tuple(map(int, done.groups())) == (pages, len(normalized), 0),
             'Consumer did not reject the recorded incomplete traversal')
    _require(done.start() >= responses[-1]['end'], 'Consumer rejection precedes terminal RESOURCE_LIMIT')
    for child, expected_code in (('consumer', 1), ('provider', 0)):
        waited = _one(serial, rb'^SSG_SESSION ' + child.encode() + rb'_wait=(-?[0-9]+) outcome=([0-9]+) code=(-?[0-9]+)\r?$', 'resource-test ' + child + ' exit')
        _require(tuple(map(int, waited.groups())) == (0, 1, expected_code) and waited.start() > done.start(),
                 'unexpected ' + child + ' outcome during resource rejection')
    _require(b'SSG_CONSUMER_TRANSPORT' not in serial, 'transport failure cannot qualify as a resource rejection')
    return {
        'status': 'PASSED_SCOPED', 'qualification': 'EXPECTED_RESOURCE_REJECTION',
        'scope': 'explicit refusal of an input exceeding the existing per-text-node budget',
        'input_sha256': input_sha256, 'oracle_structure_sha256': before['structureSha256'],
        'request_count': pages, 'successful_page_node_counts': page_counts,
        'received_prefix_nodes': len(normalized), 'terminal_status': 'RESOURCE_LIMIT',
        'text_limit': {'units': 'UTF-16 code units per text node', 'limit': 1024,
                       'oracle_over_limit_paths': [node['path'] for node in oversized],
                       'oracle_over_limit_nodes': oversized},
        'processes': {'parent_pid': parent_pid, 'provider_pid': provider_pid,
                      'consumer_pid': consumer_pid, 'source_instance': before['sourceInstance'],
                      'source_epoch': before['sourceEpoch'], 'source_revision': before['sourceRevision']},
        'checks': ['independent_before_oracle_bound_to_input_and_source', 'oversized_text_observed_in_model',
                   'complete_paired_IPC_frames', 'continuation_sources_and_cursors_match',
                   'successful_pages_match_reference_prefix', 'explicit_resource_limit_without_nodes',
                   'Consumer_rejects_incomplete_result', 'Consumer_and_Provider_exit_codes_match'],
        'oracles': [{k: oracles[0][k] for k in ('sequence', 'bytes', 'sha256')} | {'phase': 'before'}],
        'frames': [{k: record[k] for k in ('direction', 'sequence', 'bytes', 'sha256')} for record in frames],
        'structure': {'status': 'NOT_QUALIFIED', 'reason': 'input exceeds existing per-text-node limit'},
        'gate_A_overall': 'NOT_QUALIFIED', 'gate_B': 'NOT_RUN', 'gate_C': 'NOT_RUN',
    }
