# SPDX-License-Identifier: Apache-2.0
"""Publication boundaries for recovery of already uploaded SDK bytes."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import recover_glibc_sdk_release as recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.assets = self.directory / 'assets'
        self.assets.mkdir()
        self.tag = 'xos-sdk-glibc-preview-3'
        self.source = '1' * 40
        self.validator = '2' * 40
        archives = {}
        for suffix, content in (('-linux-x86_64.tar.zst', b'unit-test-binary'),
                                ('-sources.tar.zst', b'unit-test-sources')):
            name = self.tag + suffix
            (self.assets / name).write_bytes(content)
            archives[name] = {'name': name, 'sha256': recovery.sha(self.assets / name)}
        self.package = {'tag': self.tag, 'source_commit': self.source,
                        'profile_sha256': '3' * 64, 'binding': {'sdk_tree_sha256': '4' * 64},
                        'system': {'build_id': 'unit-test'},
                        'archive': archives[self.tag + '-linux-x86_64.tar.zst'],
                        'source_archive': archives[self.tag + '-sources.tar.zst']}
        self.qualification = {k: v for k, v in self.package.items() if k != 'tag'}
        self.qualification.update(status='passed', fresh_extraction_verified=True,
                                  user_data_preserved=True, applications={})
        for name, marker in (('c', 'GLIBC_KIT_C_OK 2.44'),
                             ('cpp', 'GLIBC_KIT_CPP_OK vector thread exception')):
            self.qualification['applications'][name] = {'guest_exit_code': 0, 'marker': marker,
                                                       'resources_before': [100, 3, 1],
                                                       'resources_after': [100, 3, 1]}
        recovery.write_json(self.assets / 'package.json', self.package)
        recovery.write_json(self.assets / 'qualification.json', self.qualification)
        names = sorted(recovery.asset_names(self.tag) - {'SHA256SUMS'})
        (self.assets / 'SHA256SUMS').write_text(''.join(recovery.sha(self.assets / n) + '  ' + n + '\n'
                                                      for n in names))
        self.release = {'id': 123, 'tag_name': self.tag, 'draft': True, 'prerelease': True,
                        'html_url': 'https://github.com/example/sdk/releases/tag/' + self.tag,
                        'assets': [{'id': i + 1, 'name': n, 'size': (self.assets / n).stat().st_size,
                                    'state': 'uploaded', 'digest': 'sha256:' + recovery.sha(self.assets / n)}
                                   for i, n in enumerate(sorted(recovery.asset_names(self.tag)))]}
        self.state = {'schema': 1, 'repository': 'example/sdk', 'tag': self.tag,
                      'source_commit': self.source, 'validation_commit': self.validator,
                      'release': recovery.release_snapshot(self.release, self.tag)}
        recovery.write_json(self.directory / 'download-receipt.json', self.state)
        self.environment = patch.dict(os.environ, {'GITHUB_SHA': self.validator}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def proof(self):
        with patch.object(recovery, 'qualify_archive', return_value=(self.package, self.qualification)), \
                patch('builtins.print'):
            recovery.qualify(self.directory)

    def test_original_source_is_kept_when_workflow_commit_differs(self):
        self.assertNotEqual(self.source, self.validator)
        self.assertEqual(recovery.verify_downloaded(self.directory, self.state)['source_commit'], self.source)

    def test_fresh_report_does_not_change_any_original_asset(self):
        before = {p.name: p.read_bytes() for p in self.assets.iterdir()}
        self.proof()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.assets.iterdir()})
        report = recovery.load(self.directory / 'recovery-qualification.json')
        self.assertEqual(report['source_commit'], self.source)
        self.assertEqual(report['validation_commit'], self.validator)

    def test_token_is_rejected_before_consumer_execution(self):
        with patch.dict(os.environ, {'GH_TOKEN': 'unit-test-token'}), \
                patch.object(recovery, 'qualify_archive') as consumer:
            with self.assertRaisesRegex(ValueError, 'without a GitHub token'):
                recovery.qualify(self.directory)
            consumer.assert_not_called()

    def test_original_digest_change_is_rejected(self):
        with (self.assets / 'package.json').open('ab') as stream:
            stream.write(b' ')
        with self.assertRaisesRegex(ValueError, 'size differs'):
            recovery.verify_downloaded(self.directory, self.state)

    def test_api_digest_change_is_rejected(self):
        state = copy.deepcopy(self.state)
        state['release']['assets'][0]['digest'] = 'sha256:' + '0' * 64
        with self.assertRaisesRegex(ValueError, 'API digest differs'):
            recovery.verify_downloaded(self.directory, state)

    def test_checksum_manifest_must_bind_every_other_asset(self):
        sums = self.assets / 'SHA256SUMS'
        sums.write_text(sums.read_text().splitlines()[0] + '\n')
        state = copy.deepcopy(self.state)
        item = next(a for a in state['release']['assets'] if a['name'] == 'SHA256SUMS')
        item.update(size=sums.stat().st_size, digest='sha256:' + recovery.sha(sums))
        with self.assertRaisesRegex(ValueError, 'all four other assets'):
            recovery.verify_downloaded(self.directory, state)

    def test_tag_source_mismatch_is_rejected(self):
        state = copy.deepcopy(self.state)
        state['source_commit'] = self.validator
        with self.assertRaisesRegex(ValueError, 'source differs'):
            recovery.verify_downloaded(self.directory, state)

    def test_non_draft_or_extra_asset_is_rejected(self):
        for field, value in (('draft', False), ('prerelease', False)):
            changed = copy.deepcopy(self.release)
            changed[field] = value
            with self.assertRaises(ValueError):
                recovery.release_snapshot(changed, self.tag)
        changed = copy.deepcopy(self.release)
        changed['assets'].append(changed['assets'][0])
        with self.assertRaisesRegex(ValueError, 'exactly the five'):
            recovery.release_snapshot(changed, self.tag)

    def test_guest_or_resource_failure_is_rejected(self):
        for field, value in (('guest_exit_code', 1), ('guest_exit_code', False),
                             ('resources_before', ['100', 3, 1]), ('resources_after', [99, 3, 1])):
            changed = copy.deepcopy(self.qualification)
            changed['applications']['cpp'][field] = value
            with self.assertRaisesRegex(ValueError, 'guest result differs'):
                recovery.verify_qualification(changed, self.package)

    def test_remote_asset_change_blocks_publish(self):
        self.proof()
        changed = copy.deepcopy(self.release)
        changed['assets'][0]['id'] += 100
        with patch.object(recovery, 'gh_json', return_value=changed) as api:
            with self.assertRaisesRegex(ValueError, 'changed during qualification'):
                recovery.publish(self.directory)
            self.assertEqual(api.call_count, 1)
            self.assertNotIn('PATCH', api.call_args.args)

    def test_remote_ref_change_blocks_publish(self):
        self.proof()
        with patch.object(recovery, 'gh_json', return_value=self.release) as api, \
                patch.object(recovery, 'tag_commit', return_value='9' * 40):
            with self.assertRaisesRegex(ValueError, 'tag changed'):
                recovery.publish(self.directory)
            self.assertEqual(api.call_count, 1)

    def test_publish_only_changes_the_existing_numeric_release(self):
        self.proof()
        published = {**self.release, 'draft': False}
        with patch.object(recovery, 'gh_json', side_effect=[self.release, published]) as api, \
                patch.object(recovery, 'tag_commit', return_value=self.source) as ref, patch('builtins.print'):
            recovery.publish(self.directory)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(ref.call_count, 2)
        self.assertEqual(api.call_args.args, ('repos/example/sdk/releases/123', '--method', 'PATCH',
                                             '-F', 'draft=false', '-F', 'prerelease=true', '-f', 'make_latest=false'))

    def test_publication_response_asset_change_cannot_report_success(self):
        self.proof()
        published = copy.deepcopy(self.release)
        published['draft'] = False
        published['assets'][0]['id'] += 100
        with patch.object(recovery, 'gh_json', side_effect=[self.release, published]), \
                patch.object(recovery, 'tag_commit', return_value=self.source), patch('builtins.print') as output:
            with self.assertRaisesRegex(ValueError, 'published release or assets differ'):
                recovery.publish(self.directory)
            output.assert_not_called()

    def test_post_publication_ref_change_cannot_report_success(self):
        self.proof()
        published = {**self.release, 'draft': False}
        with patch.object(recovery, 'gh_json', side_effect=[self.release, published]), \
                patch.object(recovery, 'tag_commit', side_effect=[self.source, '9' * 40]), \
                patch('builtins.print') as output:
            with self.assertRaisesRegex(ValueError, 'tag changed during publication'):
                recovery.publish(self.directory)
            output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
