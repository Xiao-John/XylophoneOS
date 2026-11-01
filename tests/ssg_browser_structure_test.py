#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic corruption tests for the validator, not guest completeness proof.

The expected tree below is written independently of its deliberately sparse IPC
IDs. Mutations are local fixtures: they are never presented as observed Provider
bugs or actual QEMU output.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ssg_browser_structure import (CANONICAL_FORMAT, SCHEMA, canonical_bytes,
                                   compare_structure, decode_capture,
                                   structure_digest, validate_capture,
                                   validate_resource_rejection)

INPUT_SHA = hashlib.sha256(b'synthetic validator fixture, not HTML input').hexdigest()
INSTANCE = '0123456789abcdef0123456789abcdef'
REFERENCE = [
    {'path': '0', 'parentPath': '', 'ordinal': 0, 'childIndex': 0, 'childCount': 2, 'tag': 'html', 'role': 'element'},
    {'path': '0/0', 'parentPath': '0', 'ordinal': 1, 'childIndex': 0, 'childCount': 1, 'tag': 'head', 'role': 'element'},
    {'path': '0/0/0', 'parentPath': '0/0', 'ordinal': 2, 'childIndex': 0, 'childCount': 1, 'tag': 'title', 'role': 'element'},
    {'path': '0/0/0/0', 'parentPath': '0/0/0', 'ordinal': 3, 'childIndex': 0, 'childCount': 0, 'tag': '', 'role': 'text', 'text': 'Reference 标题'},
    {'path': '0/1', 'parentPath': '0', 'ordinal': 4, 'childIndex': 1, 'childCount': 3, 'tag': 'body', 'role': 'element'},
    {'path': '0/1/0', 'parentPath': '0/1', 'ordinal': 5, 'childIndex': 0, 'childCount': 1, 'tag': 'div', 'role': 'element'},
    {'path': '0/1/0/0', 'parentPath': '0/1/0', 'ordinal': 6, 'childIndex': 0, 'childCount': 0, 'tag': '', 'role': 'text', 'text': 'Alpha 😀 :,\n'},
    {'path': '0/1/1', 'parentPath': '0/1', 'ordinal': 7, 'childIndex': 1, 'childCount': 1, 'tag': 'a', 'role': 'link', 'href': 'target.html?q=1&v=2'},
    {'path': '0/1/1/0', 'parentPath': '0/1/1', 'ordinal': 8, 'childIndex': 0, 'childCount': 0, 'tag': '', 'role': 'text', 'text': 'Link'},
    {'path': '0/1/2', 'parentPath': '0/1', 'ordinal': 9, 'childIndex': 2, 'childCount': 1, 'tag': 'p', 'role': 'element'},
    {'path': '0/1/2/0', 'parentPath': '0/1/2', 'ordinal': 10, 'childIndex': 0, 'childCount': 0, 'tag': '', 'role': 'text', 'text': 'Omega'},
]
IDS = ['37', '49', '50', '58', '120', '145', '146', '200', '201', '300', '301']


def consumer_nodes():
    by_path = {node['path']: IDS[i] for i, node in enumerate(REFERENCE)}
    result = []
    for i, node in enumerate(REFERENCE):
        item = {'id': IDS[i], 'parent': by_path.get(node['parentPath'], '0'),
                'tag': node['tag'], 'role': node['role'],
                'source': 'litehtml-model-and-render-layout',
                'contentTrust': 'untrusted-document-content', 'actionAuthority': 'READ_ONLY_NO_GRANT',
                'fragmentsComplete': i != 7}
        if 'text' in node:
            item.update(text=node['text'], textTruncated=False,
                        textRange=[0, len(node['text'].encode('utf-16-le')) // 2])
        if 'href' in node:
            item['href'] = node['href']
        result.append(item)
    return result


def fixture(nodes=None, page_size=4):
    nodes = consumer_nodes() if nodes is None else nodes
    oracle = {'schema': SCHEMA, 'status': 'OK', 'phase': 'before',
              'document': '/web/ssg.html', 'inputSha256': INPUT_SHA,
              'sourceInstance': INSTANCE, 'providerPid': '12', 'sourceEpoch': '50001',
              'sourceRevision': '7', 'nodeCount': len(REFERENCE), 'nodes': copy.deepcopy(REFERENCE),
              'canonicalFormat': CANONICAL_FORMAT, 'structureSha256': structure_digest(REFERENCE)}
    after = copy.deepcopy(oracle)
    after['phase'] = 'after'
    chunks = [nodes[i:i + page_size] for i in range(0, len(nodes), page_size)]
    if len(nodes) % page_size == 0:
        chunks.append([])
    requests, responses = [], []
    cursor = None
    for i, chunk in enumerate(chunks, 1):
        requests.append({'op': 'snapshot_begin', 'maxNodes': page_size} if i == 1 else
                        {'op': 'snapshot_next', 'sourceInstance': INSTANCE, 'cursor': cursor})
        complete = i == len(chunks)
        cursor = '' if complete else '50001:91:' + str(i)
        responses.append({'status': 'OK', 'sourceInstance': INSTANCE, 'providerPid': '12',
                          'sourceEpoch': '50001', 'sourceRevision': '7', 'pageSequence': str(i),
                          'sourceValid': True, 'query': '', 'visibleOnly': False, 'nodes': chunk,
                          'complete': complete, 'hasData': bool(chunk), 'hasNext': not complete,
                          'traversalComplete': complete,
                          'stopReason': 'EXHAUSTED' if complete else 'PAGE_BUDGET',
                          'baselineStatus': 'CONSUMER_MUST_VALIDATE' if complete else 'INCOMPLETE',
                          'diffStatus': 'RESET_REQUIRED_NO_PAGED_BASELINE',
                          'visited': len(chunk), 'elapsedMs': '10', 'scrollY': 0, 'cursor': cursor})
    return {'before': oracle, 'after': after, 'requests': requests, 'responses': responses}


def record(direction, sequence, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    encoded = base64.b64encode(payload)
    prefix = b'SSG_ORACLE' if direction == 'ORACLE' else b'SSG_FRAME'
    suffix = str(sequence).encode() if direction == 'ORACLE' else direction.encode() + b' ' + str(sequence).encode()
    result = prefix + b'_BEGIN ' + suffix + b' ' + str(len(payload)).encode() + b' ' + str(len(encoded)).encode() + b'\n'
    for offset in range(0, len(encoded), 96):
        result += prefix + b'_PART ' + suffix + b' ' + str(offset).encode() + b' ' + encoded[offset:offset + 96] + b'\n'
    return result + prefix + b'_END ' + suffix + b'\n'


def encode_capture(data):
    result = b'SSG_CONSUMER_START pid=11\n'
    result += ('SSG_SESSION parent=10 provider=12 consumer=11 instance=' + INSTANCE + ' text_scope=explicit\n').encode()
    result += ('SSG_PROVIDER_READY pid=12 instance=' + INSTANCE + ' text=1 kind=browser\n').encode()
    for i, (request, response) in enumerate(zip(data['requests'], data['responses']), 1):
        result += record('REQ', i, request)
        if i == 1:
            result += record('ORACLE', 1, data['before'])
        if i == len(data['responses']):
            result += record('ORACLE', 2, data['after'])
        result += record('RESP', i, response)
    result += ('SSG_PAGED_CONSUMER_DONE pages=%d nodes=%d complete=1 completeness=ORACLE_REQUIRED\n' %
               (len(data['responses']), sum(len(r['nodes']) for r in data['responses']))).encode()
    result += b'SSG_SESSION consumer_wait=0 outcome=1 code=0\nSSG_SESSION provider_wait=0 outcome=1 code=0\n'
    return result


def resource_fixture(first_page=False, long_text=None):
    data = fixture()
    del data['after']
    index = 3 if first_page else 6
    data['before']['nodes'][index]['text'] = 'x' * 1025 if long_text is None else long_text
    data['before']['structureSha256'] = structure_digest(data['before']['nodes'])
    final = {'status': 'RESOURCE_LIMIT', 'sourceInstance': INSTANCE, 'providerPid': '12'}
    data['requests'] = data['requests'][:1 if first_page else 2]
    data['responses'] = [final] if first_page else [data['responses'][0], final]
    return data


def encode_rejection(data):
    result = b'SSG_CONSUMER_START pid=11\n'
    result += ('SSG_SESSION parent=10 provider=12 consumer=11 instance=' + INSTANCE + ' text_scope=explicit\n').encode()
    result += ('SSG_PROVIDER_READY pid=12 instance=' + INSTANCE + ' text=1 kind=browser\n').encode()
    for i, (request, response) in enumerate(zip(data['requests'], data['responses']), 1):
        result += record('REQ', i, request)
        if i == 1 and 'before' in data:
            result += record('ORACLE', 1, data['before'])
        if i == len(data['responses']) and 'after' in data:
            result += record('ORACLE', 2, data['after'])
        result += record('RESP', i, response)
    result += ('SSG_PAGED_CONSUMER_DONE pages=%d nodes=%d complete=0 completeness=ORACLE_REQUIRED\n' %
               (len(data['responses']), sum(len(r.get('nodes', [])) for r in data['responses']))).encode()
    result += b'SSG_SESSION consumer_wait=0 outcome=1 code=1\nSSG_SESSION provider_wait=0 outcome=1 code=0\n'
    return result


class StructureValidatorTests(unittest.TestCase):
    def reject(self, data, fragment=None):
        with self.assertRaisesRegex(ValueError, fragment or '.'):
            validate_capture(encode_capture(data) if type(data) is dict else data, INPUT_SHA)

    def test_sparse_ids_unicode_and_incomplete_geometry_are_scoped(self):
        result = validate_capture(encode_capture(fixture()), INPUT_SHA)
        self.assertEqual(result['status'], 'PASSED_SCOPED')
        self.assertEqual(result['node_count'], 11)
        self.assertEqual(result['structure_sha256'], structure_digest(REFERENCE))
        self.assertEqual(result['rendered_fragments']['provider_claimed_incomplete_nodes'], 1)
        self.assertEqual(result['rendered_fragments']['status'], 'NOT_QUALIFIED')
        self.assertEqual(result['gate_A_overall'], 'NOT_QUALIFIED')
        self.assertEqual(result['comparison'][0]['consumerId'], '37')

    def test_exact_node_limit_has_empty_terminal_page(self):
        result = validate_capture(encode_capture(fixture(page_size=11)), INPUT_SHA)
        self.assertEqual(result['page_node_counts'], [11, 0])

    def test_netstrings_count_utf8_and_preserve_missing_fields(self):
        encoded = canonical_bytes(REFERENCE)
        self.assertTrue(encoded.startswith(b'XOS-LITEHTML-STRUCTURE-V1\n'))
        self.assertIn(b'16:Reference \xe6\xa0\x87\xe9\xa2\x98,', encoded)
        self.assertIn(b'14:Alpha \xf0\x9f\x98\x80 :,\n,', encoded)
        mutated = copy.deepcopy(REFERENCE)
        mutated[0]['text'] = ''
        self.assertNotEqual(structure_digest(mutated), structure_digest(REFERENCE))

    def test_omit_whole_subtree_even_with_consistent_completion(self):
        nodes = consumer_nodes()
        del nodes[5:7]
        self.reject(fixture(nodes), 'node count differs')

    def test_duplicate_id(self):
        nodes = consumer_nodes()
        nodes[-1]['id'] = nodes[0]['id']
        self.reject(fixture(nodes), 'duplicate Consumer')

    def test_extra_node(self):
        nodes = consumer_nodes()
        extra = copy.deepcopy(nodes[-1])
        extra['id'] = '900'
        nodes.append(extra)
        self.reject(fixture(nodes), 'node count differs')

    def test_orphan_parent(self):
        nodes = consumer_nodes()
        nodes[-1]['parent'] = '999'
        self.reject(fixture(nodes), 'missing Consumer parent')

    def test_wrong_existing_parent(self):
        nodes = consumer_nodes()
        nodes[6]['parent'] = '120'
        self.reject(fixture(nodes), 'structure mismatch')

    def test_parent_must_precede_child(self):
        nodes = consumer_nodes()
        nodes[5], nodes[6] = nodes[6], nodes[5]
        self.reject(fixture(nodes), 'missing Consumer parent')

    def test_cannot_reopen_closed_subtree(self):
        nodes = consumer_nodes()
        nodes[-1]['parent'] = '145'
        self.reject(fixture(nodes), 'closed subtree')

    def test_swap_distinct_sibling_subtrees(self):
        nodes = consumer_nodes()
        nodes[5:9] = nodes[7:9] + nodes[5:7]
        self.reject(fixture(nodes), 'structure mismatch')

    def test_wrong_root(self):
        nodes = consumer_nodes()
        nodes[0]['parent'] = '49'
        self.reject(fixture(nodes), 'root parent')

    def test_second_root(self):
        nodes = consumer_nodes()
        nodes[4]['parent'] = '0'
        self.reject(fixture(nodes), 'extra root')

    def test_one_character_text_change(self):
        nodes = consumer_nodes()
        nodes[-1]['text'] = 'Xmega'
        self.reject(fixture(nodes), 'field text')

    def test_text_truncation_flag(self):
        nodes = consumer_nodes()
        nodes[-1]['textTruncated'] = True
        self.reject(fixture(nodes), 'truncated')

    def test_utf16_text_range(self):
        nodes = consumer_nodes()
        nodes[6]['textRange'][1] -= 1
        self.reject(fixture(nodes), 'textRange')

    def test_one_character_href_change(self):
        nodes = consumer_nodes()
        nodes[7]['href'] = 'target.html?q=2&v=2'
        self.reject(fixture(nodes), 'field href')

    def test_tag_and_role_mismatch(self):
        for field, value in [('tag', 'section'), ('role', 'link')]:
            with self.subTest(field=field):
                nodes = consumer_nodes()
                nodes[5][field] = value
                self.reject(fixture(nodes))

    def test_early_completion(self):
        data = fixture()
        data['responses'][0]['complete'] = True
        self.reject(data, 'premature')

    def test_drop_terminal_page(self):
        data = fixture(page_size=11)
        del data['requests'][-1]
        del data['responses'][-1]
        self.reject(data, 'completion')

    def test_source_epoch_and_revision_drift(self):
        for field in ('sourceEpoch', 'sourceRevision', 'sourceInstance', 'providerPid'):
            with self.subTest(field=field):
                data = fixture()
                data['responses'][1][field] = '999'
                self.reject(data, 'source differs')

    def test_cursor_chain_and_reuse(self):
        data = fixture()
        data['requests'][1]['cursor'] = 'wrong'
        self.reject(data, 'cursor mismatch')
        data = fixture()
        data['responses'][1]['cursor'] = data['responses'][0]['cursor']
        self.reject(data, 'reused continuation')

    def test_filtered_or_false_typed_scope_is_rejected(self):
        for field, value in [('role', 'text'), ('visibleOnly', 0), ('maxNodes', True)]:
            with self.subTest(field=field):
                data = fixture()
                data['requests'][0][field] = value
                self.reject(data)

    def test_false_typed_flags_are_not_booleans(self):
        for field in ('complete', 'hasNext', 'hasData', 'traversalComplete', 'sourceValid', 'visibleOnly'):
            with self.subTest(field=field):
                data = fixture()
                data['responses'][0][field] = int(data['responses'][0][field])
                self.reject(data)

    def test_resource_error_cannot_be_complete(self):
        data = fixture()
        data['responses'][-1]['status'] = 'RESOURCE_LIMIT'
        self.reject(data, 'not OK')

    def test_scroll_change_and_no_progress_page(self):
        data = fixture()
        data['responses'][1]['scrollY'] = 40
        self.reject(data, 'scroll state changed')
        data = fixture()
        data['responses'][1].update(nodes=[], visited=0, hasData=False)
        self.reject(data, 'does not demonstrate progress')

    def test_input_hash_mismatch(self):
        data = fixture()
        data['before']['inputSha256'] = '0' * 64
        self.reject(data, 'input SHA-256')

    def test_oracle_changed_or_truncated(self):
        data = fixture()
        data['after']['sourceRevision'] = '8'
        self.reject(data, 'changed during paging')
        data = fixture()
        data['after']['nodes'].pop()
        self.reject(data, 'nodeCount')
        data = fixture()
        data['before']['status'] = 'ORACLE_RESOURCE_LIMIT'
        self.reject(data, 'unsuccessful')

    def test_oracle_cannot_lie_about_children_or_digest(self):
        data = fixture()
        data['before']['nodes'][4]['childCount'] = 2
        data['before']['structureSha256'] = structure_digest(data['before']['nodes'])
        self.reject(data, 'childCount')
        data = fixture()
        data['before']['structureSha256'] = 'f' * 64
        self.reject(data, 'structure SHA-256')

    def test_oracle_missing(self):
        serial = encode_capture(fixture())
        serial = b'\n'.join(line for line in serial.splitlines() if not line.startswith(b'SSG_ORACLE')) + b'\n'
        self.reject(serial, 'two ordered')

    def test_duplicate_or_orphan_or_truncated_frame(self):
        serial = encode_capture(fixture())
        first = next(line for line in serial.splitlines(keepends=True) if line.startswith(b'SSG_FRAME_BEGIN'))
        self.reject(serial.replace(first, first + first, 1), 'duplicate captured')
        part = next(line for line in serial.splitlines(keepends=True) if line.startswith(b'SSG_FRAME_PART RESP'))
        self.reject(serial.replace(part, b'', 1), 'non-contiguous')
        self.reject(serial.replace(b'SSG_FRAME_END RESP 3\n', b''), 'unterminated')
        self.reject(serial + b'SSG_FRAME_PART RESP 99 0 e30=\n', 'orphan')

    def test_json_duplicate_keys_and_invalid_base64(self):
        payload = b'{"op":"snapshot_begin","op":"snapshot_next"}'
        encoded = base64.b64encode(payload)
        serial = b'SSG_FRAME_BEGIN REQ 1 %d %d\nSSG_FRAME_PART REQ 1 0 ' % (len(payload), len(encoded)) + encoded + b'\nSSG_FRAME_END REQ 1\n'
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            decode_capture(serial)
        with self.assertRaisesRegex(ValueError, 'base64'):
            decode_capture(b'SSG_FRAME_BEGIN REQ 1 2 4\nSSG_FRAME_PART REQ 1 0 ====\nSSG_FRAME_END REQ 1\n')

    def test_unpaired_frames_and_message_sequence(self):
        serial = encode_capture(fixture())
        block = record('REQ', 2, fixture()['requests'][1])
        self.reject(serial.replace(block, b''), 'unpaired')
        self.reject(serial.replace(b'SSG_FRAME_BEGIN REQ 2 ', b'SSG_FRAME_BEGIN REQ 9 '), 'orphan')

    def test_consumer_rejection_and_unsuccessful_exits(self):
        serial = encode_capture(fixture())
        self.reject(serial.replace(b'nodes=11 complete=1', b'nodes=11 complete=0'), 'did not accept')
        for child in (b'consumer', b'provider'):
            with self.subTest(child=child):
                changed = serial.replace(child + b'_wait=0 outcome=1 code=0', child + b'_wait=0 outcome=1 code=1')
                self.reject(changed, 'did not exit successfully')

    def test_legacy_consumer_completion_cannot_qualify(self):
        serial = encode_capture(fixture())
        self.reject(serial.replace(b' completeness=ORACLE_REQUIRED', b''), 'Consumer completion')

    def test_missing_exit_or_process_identity(self):
        serial = encode_capture(fixture())
        self.reject(serial.replace(b'SSG_SESSION provider_wait=0 outcome=1 code=0\n', b''), 'provider exit')
        self.reject(serial.replace(b'parent=10 provider=12 consumer=11', b'parent=12 provider=12 consumer=11'), 'independent processes')

    def test_historical_provider_claim_without_oracle_is_unqualified(self):
        # Frozen real evidence is read-only and is not upgraded by these tests.
        import gzip
        path = Path(__file__).resolve().parents[1] / 'docs/reports/ssg_p2e_partial_20261030/observation/serial.log.gz'
        if not path.exists():
            self.skipTest('frozen historical evidence absent')
        self.reject(gzip.decompress(path.read_bytes()), 'two ordered')


class ResourceRejectionTests(unittest.TestCase):
    def reject(self, data, fragment=None):
        serial = encode_rejection(data) if type(data) is dict else data
        with self.assertRaisesRegex(ValueError, fragment or '.'):
            validate_resource_rejection(serial, INPUT_SHA)

    def test_explicit_refusal_is_scoped_and_not_A1(self):
        result = validate_resource_rejection(encode_rejection(resource_fixture()), INPUT_SHA)
        self.assertEqual(result['qualification'], 'EXPECTED_RESOURCE_REJECTION')
        self.assertEqual(result['structure']['status'], 'NOT_QUALIFIED')
        self.assertEqual(result['gate_A_overall'], 'NOT_QUALIFIED')
        self.assertEqual(result['received_prefix_nodes'], 4)
        self.assertEqual(result['text_limit']['oracle_over_limit_nodes'],
                         [{'path': '0/1/0/0', 'ordinal': 6, 'utf16_units': 1025}])
        with self.assertRaises(ValueError):
            validate_capture(encode_rejection(resource_fixture()), INPUT_SHA)

    def test_first_page_refusal_with_no_emitted_nodes(self):
        result = validate_resource_rejection(encode_rejection(resource_fixture(first_page=True)), INPUT_SHA)
        self.assertEqual(result['request_count'], 1)
        self.assertEqual(result['received_prefix_nodes'], 0)

    def test_utf16_budget_and_exact_boundary(self):
        result = validate_resource_rejection(encode_rejection(resource_fixture(long_text='😀' * 513)), INPUT_SHA)
        self.assertEqual(result['text_limit']['oracle_over_limit_nodes'][0]['utf16_units'], 1026)
        self.reject(resource_fixture(long_text='x' * 1024), 'no text beyond')

    def test_only_complete_bound_before_oracle_is_allowed(self):
        data = resource_fixture()
        del data['before']
        self.reject(data, 'exactly one before')
        data = resource_fixture()
        data['after'] = copy.deepcopy(data['before'])
        data['after']['phase'] = 'after'
        self.reject(data, 'exactly one before')
        for field, value in [('status', 'ORACLE_RESOURCE_LIMIT'), ('phase', 'after'), ('inputSha256', '0' * 64)]:
            with self.subTest(field=field):
                data = resource_fixture()
                data['before'][field] = value
                self.reject(data)

    def test_final_reply_must_explicitly_reject_without_page_fields(self):
        for status in ('OK', 'STALE_CURSOR', 'DENIED', 'SEMANTICS_UNAVAILABLE'):
            with self.subTest(status=status):
                data = resource_fixture()
                data['responses'][-1]['status'] = status
                self.reject(data, 'not RESOURCE_LIMIT')
        for field, value in [('nodes', []), ('complete', False), ('cursor', ''), ('hasNext', False)]:
            with self.subTest(field=field):
                data = resource_fixture()
                data['responses'][-1][field] = value
                self.reject(data, 'successful-page fields')

    def test_final_source_fields_are_bound_when_present(self):
        data = resource_fixture()
        data['responses'][-1].update(sourceEpoch='50001', sourceRevision='7')
        validate_resource_rejection(encode_rejection(data), INPUT_SHA)
        for field in ('sourceInstance', 'providerPid', 'sourceEpoch', 'sourceRevision'):
            with self.subTest(field=field):
                data = resource_fixture()
                data['responses'][-1][field] = '999'
                self.reject(data, 'source differs')

    def test_successful_prefix_is_independently_checked(self):
        data = resource_fixture()
        data['responses'][0]['nodes'][3]['text'] = 'Qeference 标题'
        self.reject(data, 'prefix mismatch')
        data = resource_fixture()
        data['responses'][0]['nodes'][3]['parent'] = '37'
        self.reject(data, 'prefix mismatch|extra children')
        data = resource_fixture()
        data['responses'][0]['nodes'][3]['id'] = '37'
        self.reject(data, 'duplicate Consumer')

    def test_refusal_must_occur_near_first_oversized_node(self):
        data = resource_fixture()
        data['requests'] = data['requests'][:1]
        data['responses'] = data['responses'][-1:]
        self.reject(data, 'outside the rejected page visit budget')

    def test_prior_pages_cannot_complete_or_change_scope(self):
        for field, value in [('complete', True), ('complete', 0), ('traversalComplete', True),
                             ('sourceValid', False), ('visibleOnly', True), ('status', 'RESOURCE_LIMIT'),
                             ('sourceEpoch', '999'), ('sourceRevision', '8')]:
            with self.subTest(field=field, value=value):
                data = resource_fixture()
                data['responses'][0][field] = value
                self.reject(data)
        data = resource_fixture()
        data['requests'][0]['role'] = 'text'
        self.reject(data, 'unfiltered')

    def test_requests_and_continuations_are_bound(self):
        for field, value in [('cursor', 'wrong'), ('sourceInstance', 'f' * 32), ('op', 'snapshot_cancel')]:
            with self.subTest(field=field):
                data = resource_fixture()
                data['requests'][1][field] = value
                self.reject(data, 'continuation')
        serial = encode_rejection(resource_fixture())
        self.reject(serial.replace(record('REQ', 2, resource_fixture()['requests'][1]), b''), 'unpaired')
        self.reject(serial.replace(b'SSG_FRAME_END RESP 2\n', b''), 'unterminated')

    def test_consumer_counts_and_completion_must_match(self):
        serial = encode_rejection(resource_fixture())
        for original, changed in [(b'pages=2 nodes=4', b'pages=1 nodes=4'),
                                  (b'pages=2 nodes=4', b'pages=2 nodes=3'),
                                  (b'complete=0 completeness=', b'complete=1 completeness=')]:
            with self.subTest(changed=changed):
                self.reject(serial.replace(original, changed), 'did not reject')
        self.reject(serial.replace(b' completeness=ORACLE_REQUIRED', b''), 'Consumer result')

    def test_scope_and_three_process_identities_are_required(self):
        serial = encode_rejection(resource_fixture())
        for original, changed in [(b'text_scope=explicit', b'text_scope=denied'),
                                  (b'text=1 kind=browser', b'text=0 kind=browser'),
                                  (b'parent=10 provider=12 consumer=11', b'parent=12 provider=12 consumer=11'),
                                  (b'SSG_CONSUMER_START pid=11', b'SSG_CONSUMER_START pid=20'),
                                  (b'SSG_PROVIDER_READY pid=12', b'SSG_PROVIDER_READY pid=20')]:
            with self.subTest(changed=changed):
                self.reject(serial.replace(original, changed))

    def test_every_exit_outcome_must_be_unique_and_expected(self):
        serial = encode_rejection(resource_fixture())
        for original, changed in [(b'consumer_wait=0 outcome=1 code=1', b'consumer_wait=0 outcome=1 code=0'),
                                  (b'provider_wait=0 outcome=1 code=0', b'provider_wait=0 outcome=1 code=1'),
                                  (b'consumer_wait=0 outcome=1 code=1', b'consumer_wait=-1 outcome=1 code=1'),
                                  (b'provider_wait=0 outcome=1 code=0', b'provider_wait=0 outcome=2 code=0')]:
            with self.subTest(changed=changed):
                self.reject(serial.replace(original, changed), 'unexpected .* outcome')
        self.reject(serial + b'SSG_SESSION consumer_wait=0 outcome=1 code=0\n', 'exactly one')
        self.reject(serial + b'SSG_SESSION provider_wait=broken\n', 'exactly one')
        self.reject(serial.replace(b'SSG_SESSION provider_wait=0 outcome=1 code=0\n', b''), 'exactly one')

    def test_transport_failure_is_not_expected_resource_refusal(self):
        serial = encode_rejection(resource_fixture())
        self.reject(serial + b'SSG_CONSUMER_TRANSPORT seq=2 result=TIMEOUT received=0\n', 'transport failure')

    def test_plain_success_capture_cannot_be_resource_qualification(self):
        self.reject(encode_capture(fixture()), 'exactly one before')


if __name__ == '__main__':
    unittest.main(verbosity=2)
