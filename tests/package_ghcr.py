# SPDX-License-Identifier: Apache-2.0
"""Host GHCR protocol and real XPK verification with a controlled HTTP seam."""
import hashlib
from io import BytesIO
import json
from email.message import Message
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import package_p3_repository as fixtures_module
from xypm_format import PackageError
from xypm_ghcr import EMPTY_CONFIG, MANIFEST, XPK, fetch_package, open_ghcr


class Reply(BytesIO):
    status = 200

    def __init__(self, data):
        super().__init__(data)
        self.headers = Message()


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


class GhcrCases(unittest.TestCase):
    def setUp(self):
        fixtures = fixtures_module.repository_cases()
        fixtures.setUp()
        self.addCleanup(fixtures.tearDown)
        self.body = fixtures.base.read_bytes()
        self.output = fixtures.folder / 'fetched.xpk'
        self.manifest = json.dumps({
            'schemaVersion': 2, 'mediaType': MANIFEST, 'artifactType': XPK, 'config': EMPTY_CONFIG,
            'layers': [{'mediaType': XPK, 'digest': digest(self.body), 'size': len(self.body)}],
        }).encode()

    def fetch(self, *, manifest=None, blob=None):
        def request(path, **options):
            if path.startswith('/token?'):
                self.assertFalse(options)
                return Reply(b'{"token":"fixture"}')
            self.assertEqual(options.get('token'), 'fixture')
            if '/manifests/' in path:
                self.assertTrue(path.endswith(digest(self.manifest)))
                return Reply(self.manifest if manifest is None else manifest)
            self.assertTrue(path.endswith(digest(self.body)))
            return Reply(self.body if blob is None else blob)

        return fetch_package('test/packages', digest(self.manifest), self.output, fixtures_module.profile, request=request)

    def test_verified_package(self):
        self.assertEqual(self.fetch()['package_id'], 'friends.base')
        self.assertEqual(self.output.read_bytes(), self.body)
        with self.assertRaises(PackageError):
            self.fetch()

    def test_blob_redirect_drops_bearer(self):
        original = 'https://ghcr.io/v2/test/packages/blobs/' + digest(self.body)
        locations = Message()
        locations['Location'] = 'https://pkg-containers.githubusercontent.com/blob'
        error = HTTPError(original, 307, 'redirect', locations, BytesIO())
        with patch('xypm_ghcr.build_opener') as opener:
            opener.return_value.open.side_effect = [error, Reply(self.body)]
            with open_ghcr(original.removeprefix('https://ghcr.io'), token='fixture', blob=True):
                pass
            first, second = [call.args[0] for call in opener.return_value.open.call_args_list]
            self.assertEqual(first.get_header('Authorization'), 'Bearer fixture')
            self.assertIsNone(second.get_header('Authorization'))
        locations.replace_header('Location', 'https://example.org/blob')
        with patch('xypm_ghcr.build_opener') as opener:
            opener.return_value.open.side_effect = HTTPError(original, 307, 'redirect', locations, BytesIO())
            with self.assertRaises(PackageError):
                open_ghcr(original.removeprefix('https://ghcr.io'), token='fixture', blob=True)
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_bad_inputs_leave_no_output(self):
        altered = bytes([self.body[0] ^ 1]) + self.body[1:]
        for inputs in ({'manifest': self.manifest + b' '}, {'blob': self.body[:-1]},
                       {'blob': self.body + b'x'}, {'blob': altered}):
            with self.subTest(case=list(inputs)):
                with self.assertRaises(PackageError):
                    self.fetch(**inputs)
                self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
