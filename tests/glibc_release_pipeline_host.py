# SPDX-License-Identifier: Apache-2.0
"""Release routing, bound receipts and atomic artifact copies; no guest claim."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import glibc_release_pipeline as pipeline
from package_application_preview import artifact
from xypm_format import canonical, sha_file


class release_pipeline_cases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='xos_release_pipeline_')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_default_refuses_historical_package_arguments(self):
        result = subprocess.run(['bash', ROOT / 'scripts/release_pipeline.sh', 'package',
                                 '--dash-manifest', 'historical.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('requires exactly one --release-dir', result.stderr)

    def test_explicit_historical_route_remains_available(self):
        result = subprocess.run(['bash', ROOT / 'scripts/release_pipeline.sh', '--newlib',
                                 'package', '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--dash-manifest', result.stdout)

    def test_default_smoke_cannot_use_implicit_historical_directory(self):
        result = subprocess.run(['bash', ROOT / 'scripts/release_pipeline.sh', 'smoke'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('--glibc-release', result.stderr)

    def test_build_requests_both_real_guest_gates(self):
        command = pipeline.command('build', ['--output', 'candidate', '--glibc-app-kit', 'kit',
                                             '--glibc-daily-source', 'sbase'])
        self.assertEqual(command.count('--guest'), 1)
        self.assertEqual(command.count('--installer-guest'), 1)
        explicit = pipeline.command('build', command[2:])
        self.assertEqual(explicit.count('--guest'), 1)
        self.assertEqual(explicit.count('--installer-guest'), 1)

    def test_option_values_remain_single_arguments(self):
        args = ['--release-dir', 'a space/$literal', '--glibc-candidate=candidate',
                '--glibc-app-kit', 'kit;literal', '--cpython-package', 'python.xpk']
        self.assertEqual(pipeline.command('package', args)[2:], args)
        for extra in ('--release-dir=other', '--glibc-app-kit=other'):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                pipeline.command('package', [*args, extra])

    def test_incomplete_materials_cannot_reach_freeze(self):
        with self.assertRaisesRegex(ValueError, '--glibc-source'):
            pipeline.command('materials', ['--release', 'r', '--components', 'c',
                                            '--xypm-relink', 'x'])

    def write_inputs(self):
        source = self.root / 'inputs'
        source.mkdir()
        paths = {}
        for name, body in [('images.tar.gz', b'host transaction fixture\x00'),
                           ('application-sdk.tar.gz', b'another host fixture\n')]:
            path = source / name
            path.write_bytes(body)
            paths[name] = path
        return paths, {name: artifact(path) for name, path in paths.items()}

    def test_atomic_copy_and_checksums_keep_inputs(self):
        paths, records = self.write_inputs()
        target = self.root / 'frozen'
        receipt = {'scope': 'host fixture, not a runtime or release qualification', 'assets': records}
        complete = pipeline.freeze_files(target, paths, records, receipt)
        self.assertEqual({path.name for path in target.iterdir()},
                         {*records, pipeline.RECEIPT, pipeline.CHECKSUMS})
        self.assertEqual((target / pipeline.CHECKSUMS).read_bytes(), pipeline.checksum_bytes(complete))
        for name in records:
            self.assertEqual(artifact(paths[name]), records[name])
            self.assertEqual(artifact(target / name), records[name])
        with self.assertRaisesRegex(ValueError, 'new frozen output'):
            pipeline.freeze_files(target, paths, records, receipt)

    def test_changed_input_leaves_no_output_or_staging(self):
        paths, records = self.write_inputs()
        next(iter(paths.values())).write_bytes(b'changed after binding')
        with self.assertRaisesRegex(ValueError, 'input changed while freezing'):
            pipeline.freeze_files(self.root / 'frozen', paths, records, {})
        self.assertEqual({path.name for path in self.root.iterdir()}, {'inputs'})

    def test_missing_input_leaves_no_output(self):
        paths, records = self.write_inputs()
        list(paths.values())[-1].unlink()
        with self.assertRaises(FileNotFoundError):
            pipeline.freeze_files(self.root / 'frozen', paths, records, {})
        self.assertFalse((self.root / 'frozen').exists())

    def test_no_replace_publication_preserves_racing_empty_directory(self):
        source, target = self.root / 'staging', self.root / 'raced'
        source.mkdir()
        (source / 'data').write_bytes(b'private staging')
        target.mkdir()
        with self.assertRaises(FileExistsError):
            pipeline.publish_directory(source, target)
        self.assertTrue((source / 'data').is_file())
        self.assertEqual(list(target.iterdir()), [])

    def test_asset_paths_cannot_escape_or_inject_checksum_lines(self):
        for name in ('../asset', '/asset', 'a/b', 'a\\b', 'x\nnew', '..', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                pipeline.flat_name(name)

    def distribution_fixture(self):
        base, extra = self.root / 'release', self.root / 'supplements'
        base.mkdir()
        extra.mkdir()
        names = ('images.tar.gz', 'application-sdk.tar.gz', 'packages.tar.gz',
                 'gnu-seed-sources.tar.gz', 'system_manifest.json')
        for name in names:
            (base / name).write_bytes(b'host binding fixture: ' + name.encode())
        release = {'schema_version': 1, 'status': 'assembled_glibc_candidate', 'gnu_seed': {},
                   'archives': {name: artifact(base / name) for name in names[:-1]},
                   'system': {'manifest_sha256': sha_file(base / 'system_manifest.json')}}
        (base / pipeline.MANIFEST).write_bytes(canonical(release))
        from package_glibc_release import release_checksums
        (base / pipeline.CHECKSUMS).write_bytes(release_checksums(base, release))
        assets = {name: artifact(base / name) for name in (*names, pipeline.MANIFEST)}
        names = (pipeline.SOURCES, pipeline.SOURCES_MANIFEST, pipeline.RELINK, pipeline.DASH_RELINK,
                 pipeline.DAILY_RELINK, pipeline.GNU_MAKE_RELINK, pipeline.CPYTHON_RELINK,
                 'glibc-source.tar.gz')
        for name in names:
            (extra / name).write_bytes(b'host supplement fixture: ' + name.encode())
        supplements = {name: artifact(extra / name) for name in names}
        receipt = {'format': 'xos_glibc_release_supplements_v6', 'base_assets': assets,
                   'release_manifest_sha256': assets[pipeline.MANIFEST]['sha256'],
                   'glibc_source': {'archive': 'glibc-source.tar.gz'}, 'supplements': supplements}
        (extra / pipeline.DISTRIBUTION).write_bytes(canonical(receipt))
        (extra / pipeline.CHECKSUMS).write_bytes(pipeline.checksum_bytes(
            {**assets, **supplements, pipeline.DISTRIBUTION: artifact(extra / pipeline.DISTRIBUTION)}))
        return base, extra

    def test_complete_material_inventory_is_byte_bound(self):
        base, extra = self.distribution_fixture()
        _, paths, records = pipeline.distribution_files(base, extra)
        self.assertEqual(len(paths), 15)
        self.assertEqual(set(paths), set(records))
        (extra / pipeline.CPYTHON_RELINK).write_bytes(b'changed relink archive')
        with self.assertRaisesRegex(ValueError, 'distribution asset differs'):
            pipeline.distribution_files(base, extra)

    def test_old_or_other_release_materials_are_rejected(self):
        base, extra = self.distribution_fixture()
        path = extra / pipeline.DISTRIBUTION
        original = json.loads(path.read_bytes())
        for field, value in (('format', 'xos_glibc_release_supplements_v1'),
                             ('release_manifest_sha256', '0' * 64)):
            changed = {**original, field: value}
            path.write_bytes(canonical(changed))
            with self.subTest(field=field), self.assertRaises(ValueError):
                pipeline.distribution_files(base, extra)

    def smoke_fixture(self):
        release = {'work_disk': {'sha256': 'd' * 64}, 'system': {'iso': {'sha256': '1' * 64}},
                   'installer_iso': {'sha256': '2' * 64},
                   'application_sdk': {'profile_sha256': '3' * 64}}
        digest = 'a' * 64
        package = {'status': 'passed_subset', 'release_manifest_sha256': digest,
                   'assembled_disk_sha256': 'd' * 64, 'ordinary_iso_sha256': '1' * 64,
                   'installer_iso_sha256': '2' * 64, 'profile_sha256': '3' * 64,
                   'checks': ['host fixture only']}
        seed = {'status': 'passed_subset', 'release_manifest_sha256': digest,
                'initial_disk_sha256': 'd' * 64, 'cases': ['host fixture only']}
        (self.root / 'gnu_seed').mkdir()
        (self.root / 'report.json').write_bytes(canonical(package))
        (self.root / 'gnu_seed/report.json').write_bytes(canonical(seed))
        combined = {'status': 'passed_subset', 'release_manifest_sha256': digest,
                    'work_disk_sha256': 'd' * 64, 'package_checks': package['checks'],
                    'gnu_seed_cases': 1, 'packages_sha256': sha_file(self.root / 'report.json'),
                    'gnu_seed_sha256': sha_file(self.root / 'gnu_seed/report.json')}
        (self.root / 'combined_report.json').write_bytes(canonical(combined))
        return release, digest

    def test_smoke_requires_same_release_disk_profile_and_raw_reports(self):
        release, digest = self.smoke_fixture()
        paths, records = pipeline.smoke_files(self.root, release, digest)
        self.assertEqual(len(paths), 3)
        self.assertEqual(set(paths), set(records))
        for field, value in (('work_disk', {'sha256': '0' * 64}),
                             ('application_sdk', {'profile_sha256': '0' * 64})):
            other = copy.deepcopy(release)
            other[field] = value
            with self.assertRaises(ValueError):
                pipeline.smoke_files(self.root, other, digest)
        with self.assertRaisesRegex(ValueError, 'different release'):
            pipeline.smoke_files(self.root, release, 'f' * 64)
        package = json.loads((self.root / 'report.json').read_bytes())
        package['checks'].append('altered')
        (self.root / 'report.json').write_bytes(canonical(package))
        with self.assertRaisesRegex(ValueError, 'combined smoke binding differs'):
            pipeline.smoke_files(self.root, release, digest)

    def test_failed_smoke_is_not_promoted(self):
        release, digest = self.smoke_fixture()
        path = self.root / 'gnu_seed/report.json'
        report = json.loads(path.read_bytes())
        report['status'] = 'failed'
        path.write_bytes(canonical(report))
        with self.assertRaisesRegex(ValueError, 'both pass'):
            pipeline.smoke_files(self.root, release, digest)

    def test_license_gate_rejects_another_build_before_running_audit(self):
        build = self.root / 'build'
        build.mkdir()
        manifest = build / 'manifest.json'
        manifest.write_bytes(b'{"build_id":"bound_fixture"}\n')
        release = {'system': {'manifest_sha256': sha_file(manifest)}}
        self.assertEqual(pipeline.license_command(build, release)[-2:], ['--build', str(build)])
        manifest.write_bytes(b'{"build_id":"different_fixture"}\n')
        with self.assertRaisesRegex(ValueError, 'license build manifest differs'):
            pipeline.license_command(build, release)

    def test_report_replaced_during_validation_is_rejected(self):
        release, digest = self.smoke_fixture()
        original = pipeline.metadata_snapshot

        def replace_after_read(path):
            result = original(path)
            if path.name == 'combined_report.json':
                (self.root / 'report.json').write_bytes(b'{"status":"failed"}\n')
            return result

        with mock.patch.object(pipeline, 'metadata_snapshot', replace_after_read):
            with self.assertRaisesRegex(ValueError, 'smoke report changed'):
                pipeline.smoke_files(self.root, release, digest)

    def test_report_replaced_after_validation_keeps_original_binding(self):
        release, digest = self.smoke_fixture()
        paths, records = pipeline.smoke_files(self.root, release, digest)
        (self.root / 'report.json').write_bytes(b'{"status":"failed"}\n')
        with self.assertRaisesRegex(ValueError, 'input changed while freezing'):
            pipeline.freeze_files(self.root / 'frozen', paths, records, {})
        self.assertFalse((self.root / 'frozen').exists())

    def test_supplement_receipt_replaced_after_read_is_rejected(self):
        base, extra = self.distribution_fixture()
        original = pipeline.metadata_snapshot

        def replace_after_read(path):
            result = original(path)
            if path.name == pipeline.DISTRIBUTION:
                path.write_bytes(b'{"format":"changed"}\n')
            return result

        with mock.patch.object(pipeline, 'metadata_snapshot', replace_after_read):
            with self.assertRaisesRegex(ValueError, 'distribution asset differs'):
                pipeline.distribution_files(base, extra)

    def test_real_bundled_newlib_sdk_cannot_be_glibc_kit(self):
        # This check runs only in the user-selected prerelease SDK environment.
        bundled = Path('/opt/xos/sysroot')
        if not bundled.is_dir():
            self.skipTest('prerelease SDK is not mounted')
        from build_candidate import inspect_app_kit
        with self.assertRaises((OSError, ValueError)):
            inspect_app_kit(bundled)


if __name__ == '__main__':
    unittest.main(verbosity=2)
