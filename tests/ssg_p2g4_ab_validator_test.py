#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic A/B corruption tests; these are not guest qualification."""
import unittest

from ssg_browser_structure import decode_capture, latest_ab_nodes, validate_ab_capture
from ssg_browser_structure_test import INPUT_SHA, INSTANCE, fixture, record


def encode_ab(mutate=None, omit_last_oracle=False):
    sessions = [fixture(), fixture()]
    for ordinal, data in enumerate(sessions):
        for response in data['responses']:
            response['sessionId'] = str(ordinal + 1)
            response['scrollY'] = ordinal * 20
        if ordinal:
            data['before']['sourceRevision'] = '8'
            data['after']['sourceRevision'] = '8'
            for response in data['responses']:
                response['sourceRevision'] = '8'
    if mutate:
        mutate(sessions)
    serial = b'SSG_CONSUMER_START pid=11\n'
    serial += ('SSG_SESSION parent=10 provider=12 consumer=11 instance=' + INSTANCE + ' text_scope=explicit\n').encode()
    serial += ('SSG_PROVIDER_READY pid=12 instance=' + INSTANCE + ' text=1 kind=browser\n').encode()
    sequence = 0
    for ordinal, data in enumerate(sessions):
        for i, (request, response) in enumerate(zip(data['requests'], data['responses'])):
            sequence += 1
            serial += record('REQ', sequence, request)
            if i == 0:
                serial += record('ORACLE', ordinal * 2 + 1, data['before'])
            if i == len(data['responses']) - 1 and not (ordinal == 1 and omit_last_oracle):
                serial += record('ORACLE', ordinal * 2 + 2, data['after'])
            serial += record('RESP', sequence, response)
        serial += ('SSG_BASELINE_' + 'AB'[ordinal] + '_COMMITTED nodes=11 instance=' + INSTANCE +
                   ' epoch=50001 revision=' + str(7 + ordinal) + ' session=' + str(ordinal + 1) +
                   ' scrollY=' + str(ordinal * 20) + '\n').encode()
    serial += b'SSG_CONSUMER_DIFF_DONE status=OK\n'
    serial += b'SSG_SESSION consumer_wait=0 outcome=1 code=0\nSSG_SESSION provider_wait=0 outcome=1 code=0\n'
    return serial


class ab_validator_tests(unittest.TestCase):
    def test_two_complete_sessions_match_independent_oracles(self):
        result = validate_ab_capture(encode_ab(), INPUT_SHA)
        self.assertEqual(result['status'], 'PASSED_SCOPED')
        self.assertEqual([x['nodes'] for x in result['comparisons']], [11, 11])
        self.assertEqual(len(latest_ab_nodes(decode_capture(encode_ab()))), 11)

    def test_missing_oracle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'four ordered'):
            validate_ab_capture(encode_ab(omit_last_oracle=True), INPUT_SHA)

    def test_changed_oracle_or_input_is_rejected(self):
        def mutate(sessions):
            sessions[1]['after']['sourceRevision'] = '9'
        with self.assertRaises(ValueError):
            validate_ab_capture(encode_ab(mutate), INPUT_SHA)
        with self.assertRaises(ValueError):
            validate_ab_capture(encode_ab(), '0' * 64)

    def test_missing_node_and_bad_cursor_are_rejected(self):
        def missing(sessions):
            sessions[1]['responses'][0]['nodes'].pop()
        def cursor(sessions):
            sessions[1]['requests'][1]['cursor'] = 'wrong'
        for mutate in (missing, cursor):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                validate_ab_capture(encode_ab(mutate), INPUT_SHA)

    def test_reused_session_or_scroll_is_rejected(self):
        def mutate(sessions):
            for response in sessions[1]['responses']:
                response['sessionId'] = '1'
                response['scrollY'] = 0
        with self.assertRaises(ValueError):
            validate_ab_capture(encode_ab(mutate), INPUT_SHA)


if __name__ == '__main__':
    unittest.main()
