# SPDX-License-Identifier: Apache-2.0
"""Replay offline P3 repositories through Python and the real native verifier."""
import argparse
import copy
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from make_work_disk import make_image
from xypm_format import (DEFAULT_PROFILE, PackageError, canonical, load_json,
                        pack_package, sha_file, verify_package)
from xypm_image import query_image, transact
from xypm_repository import (create_repository, make_lock, resolve, transact_locked,
                            validate_index, verify_repository, write_metadata)

profile = load_json(DEFAULT_PROFILE)
native_binary = None
case_results = []


class repository_cases(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='xypm_p3_')
        self.folder = Path(self.temporary.name)
        self.serial = 0
        self.base = self.package('friends.base')
        self.base_hash = sha_file(self.base)
        self.dependency = {'id': 'friends.base', 'upstream_version': '1.0',
                           'revision': 0, 'sha256': self.base_hash}
        self.application = self.package('friends.app', dependencies=[self.dependency])
        self.application_hash = sha_file(self.application)
        self.repository = self.folder / 'repository'
        create_repository([self.application, self.base], self.repository, profile)
        self.lock_path = self.folder / 'lock.json'
        self.lock = make_lock(self.repository, [self.application_hash], profile)
        write_metadata(self.lock_path, self.lock)

    def tearDown(self):
        self.temporary.cleanup()

    def package(self, name, revision=0, dependencies=None, version='1.0', target_profile=None, members=0):
        self.serial += 1
        stage = self.folder / ('stage_%d' % self.serial)
        files = {'usr/share/%s/data' % name: b'package content\n',
                 'usr/share/%s/LICENSE' % name: b'Apache-2.0 fixture\n',
                 'usr/share/%s/receipt.json' % name: b'{"status":"fixture"}\n'}
        for ordinal in range(members):
            files['usr/share/%s/member_%04d' % (name, ordinal)] = b'member bytes\n'
        entries = []
        for path, body in files.items():
            destination = stage / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
            entries.append({'path': path, 'type': 'file', 'size': len(body),
                            'sha256': hashlib.sha256(body).hexdigest(), 'role': 'data'})
        receipt = 'usr/share/%s/receipt.json' % name
        manifest = {'format_version': 1, 'id': name, 'upstream_version': version,
                    'revision': revision, 'target_profile': target_profile or profile['id'],
                    'required_features': [], 'runtime_dependencies': dependencies or [],
                    'files': entries, 'licenses': ['usr/share/%s/LICENSE' % name],
                    'build_receipt': {'path': receipt, 'sha256': hashlib.sha256(files[receipt]).hexdigest()},
                    'source': 'generated offline repository fixture'}
        output = self.folder / ('package_%d.xpk' % self.serial)
        pack_package(stage, manifest, output)
        return output

    def check_both(self, good, expected=None):
        try:
            result = verify_repository(self.repository, self.lock_path, profile, expected)
            host_ok, host_error = True, ''
        except (ValueError, OSError, KeyError, TypeError) as error:
            host_ok, host_error, result = False, str(error), None
        command = [str(native_binary), str(self.repository), str(self.lock_path)]
        if expected is not None:
            command.append(expected)
        native = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertIn(native.returncode, (0, 3), native.stderr)
        native_ok = native.returncode == 0
        case_results.append({'case': self.id().split('.')[-1], 'expected': good,
                             'host': host_ok, 'native_host': native_ok,
                             'host_error': host_error, 'native_error': native.stderr.strip()})
        self.assertEqual((host_ok, native_ok), (good, good), (host_error, native.stderr))
        if good:
            self.assertEqual(native.stdout.splitlines(), [entry['sha256'] for entry in result['packages']])

    def replace_index(self, change, repair_lock=True):
        path = self.repository / 'index.json'
        index = load_json(path)
        change(index)
        path.write_bytes(canonical(index))
        if repair_lock:
            self.lock['index_sha256'] = sha_file(path)
            self.lock_path.write_bytes(canonical(self.lock))

    def test_valid_dependency_order_and_trusted_pin(self):
        self.assertEqual(self.lock['packages'], [self.base_hash, self.application_hash])
        self.check_both(True, sha_file(self.lock_path))

    def test_deterministic_repository_and_lock(self):
        second = self.folder / 'second'
        create_repository([self.base, self.application], second, profile)
        self.assertEqual((second / 'index.json').read_bytes(), (self.repository / 'index.json').read_bytes())
        self.assertEqual(make_lock(second, [self.application_hash], profile), self.lock)
        self.check_both(True)

    def test_wrong_lock_pin(self):
        self.check_both(False, '0' * 64)

    def test_invalid_lock_pin(self):
        self.check_both(False, 'not-a-hash')

    def test_mixed_index(self):
        self.replace_index(lambda index: index.update(target_profile='other-profile'))
        self.check_both(False)

    def test_changed_index_bytes(self):
        with (self.repository / 'index.json').open('ab') as stream:
            stream.write(b' ')
        self.check_both(False)

    def test_missing_package(self):
        (self.repository / (self.base_hash + '.xpk')).unlink()
        self.check_both(False)

    def test_tampered_package(self):
        path = self.repository / (self.base_hash + '.xpk')
        data = bytearray(path.read_bytes()); data[6000] ^= 1; path.write_bytes(data)
        self.check_both(False)

    def test_package_symlink(self):
        path = self.repository / (self.base_hash + '.xpk'); path.unlink(); path.symlink_to(self.base)
        self.check_both(False)

    def test_index_symlink(self):
        path = self.repository / 'index.json'; saved = self.folder / 'other.json'
        path.rename(saved); path.symlink_to(saved)
        self.check_both(False)

    def test_lock_symlink(self):
        saved = self.folder / 'other.json'; self.lock_path.rename(saved); self.lock_path.symlink_to(saved)
        self.check_both(False)

    def test_oversized_index(self):
        (self.repository / 'index.json').write_bytes(b' ' * ((1 << 20) + 1))
        self.check_both(False)

    def test_oversized_lock(self):
        self.lock_path.write_bytes(b' ' * ((1 << 20) + 1))
        self.check_both(False)

    def test_duplicate_json_keys(self):
        path = self.repository / 'index.json'
        path.write_bytes(b'{"format_version":1,' + path.read_bytes()[1:])
        self.check_both(False)

    def test_unknown_metadata_field(self):
        self.replace_index(lambda index: index['packages'][0].update(path='../escape.xpk'))
        self.check_both(False)

    def test_boolean_version(self):
        self.replace_index(lambda index: index.update(format_version=True))
        self.check_both(False)

    def test_invalid_size(self):
        self.replace_index(lambda index: index['packages'][0].update(size=513))
        self.check_both(False)

    def test_metadata_size_differs(self):
        self.replace_index(lambda index: index['packages'][0].update(size=index['packages'][0]['size'] + 512))
        self.check_both(False)

    def test_metadata_version_differs(self):
        self.replace_index(lambda index: next(entry for entry in index['packages'] if entry['id'] == 'friends.app').update(upstream_version='changed'))
        self.check_both(False)

    def test_metadata_features_differ(self):
        self.replace_index(lambda index: index['packages'][0].update(required_features=['file_io']))
        self.check_both(False)

    def test_metadata_dependencies_differ(self):
        self.replace_index(lambda index: next(entry for entry in index['packages'] if entry['id'] == 'friends.app').update(runtime_dependencies=[]))
        self.lock['packages'] = [self.application_hash]; self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_dependency_identity_mismatch(self):
        self.replace_index(lambda index: next(entry for entry in index['packages'] if entry['id'] == 'friends.app')['runtime_dependencies'][0].update(revision=1))
        self.check_both(False)

    def test_missing_dependency_in_index(self):
        self.replace_index(lambda index: index.update(packages=[entry for entry in index['packages'] if entry['id'] == 'friends.app']))
        self.check_both(False)

    def test_duplicate_repository_entry(self):
        self.replace_index(lambda index: index['packages'].insert(0, copy.deepcopy(index['packages'][0])))
        self.check_both(False)

    def test_ambiguous_package_identity(self):
        def change(index):
            duplicate = copy.deepcopy(index['packages'][0]); duplicate['sha256'] = 'f' * 64
            index['packages'].append(duplicate); index['packages'].sort(key=lambda entry: entry['sha256'])
        self.replace_index(change)
        self.check_both(False)

    def test_unsorted_repository(self):
        self.replace_index(lambda index: index['packages'].reverse())
        self.check_both(False)

    def test_cycle(self):
        def change(index):
            base = next(entry for entry in index['packages'] if entry['id'] == 'friends.base')
            base['runtime_dependencies'] = [{'id': 'friends.app', 'upstream_version': '1.0',
                                             'revision': 0, 'sha256': self.application_hash}]
        self.replace_index(change)
        self.check_both(False)

    def test_conflicting_versions(self):
        other = self.package('friends.base', revision=1)
        replacement = self.folder / 'replacement'
        create_repository([self.application, self.base, other], replacement, profile)
        shutil.rmtree(self.repository); replacement.rename(self.repository)
        self.lock['index_sha256'] = sha_file(self.repository / 'index.json')
        self.lock['roots'] = sorted([self.application_hash, sha_file(other)])
        self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_wrong_lock_order(self):
        self.lock['packages'].reverse(); self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_incomplete_lock(self):
        self.lock['packages'].pop(0); self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_duplicate_lock_root(self):
        self.lock['roots'] *= 2; self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_unknown_lock_fields(self):
        self.lock['download'] = 'https://example.invalid/package'; self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_invalid_utf8(self):
        self.lock_path.write_bytes(b'"\xff"')
        self.check_both(False)

    def test_deep_metadata(self):
        self.lock_path.write_bytes(b'[' * 10 + b'0' + b']' * 10)
        self.check_both(False)

    def test_duplicate_source_preserves_no_incomplete_repository(self):
        output = self.folder / 'rejected'
        with self.assertRaises((ValueError, OSError)):
            create_repository([self.base, self.base], output, profile)
        self.assertFalse(output.exists())

    def test_existing_output_preserved(self):
        before = sha_file(self.repository / 'index.json')
        with self.assertRaises(OSError):
            create_repository([self.base], self.repository, profile)
        self.assertEqual(sha_file(self.repository / 'index.json'), before)
        before = sha_file(self.lock_path)
        with self.assertRaises(OSError):
            write_metadata(self.lock_path, {})
        self.assertEqual(sha_file(self.lock_path), before)

    def test_utf8_opaque_version(self):
        package = self.package('friends.unicode', version='版本 1.0 🎵')
        replacement = self.folder / 'replacement'
        create_repository([package], replacement, profile)
        shutil.rmtree(self.repository); replacement.rename(self.repository)
        self.lock = make_lock(self.repository, [sha_file(package)], profile)
        self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(True)

    def test_utf8_version_character_boundary(self):
        package = self.package('friends.unicode', version='🎵' * 1024)
        replacement = self.folder / 'replacement'
        create_repository([package], replacement, profile)
        shutil.rmtree(self.repository); replacement.rename(self.repository)
        self.lock = make_lock(self.repository, [sha_file(package)], profile)
        self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(True)

    def test_utf8_version_over_boundary(self):
        self.replace_index(lambda index: index['packages'][0].update(upstream_version='🎵' * 1025))
        self.check_both(False)

    def test_repository_entry_budget(self):
        def change(index):
            prototype = index['packages'][0]
            index['packages'] = [dict(prototype, id='friends.p%d' % i, sha256='%064x' % i)
                                 for i in range(257)]
        self.replace_index(change)
        self.check_both(False)

    def test_selected_closure_budget(self):
        def change(index):
            prototype = index['packages'][0]
            entries = []
            for i in range(65):
                dependency = [] if i == 64 else [{'id': 'friends.p%d' % (i + 1),
                    'upstream_version': prototype['upstream_version'], 'revision': prototype['revision'],
                    'sha256': '%064x' % (i + 2)}]
                entries.append(dict(prototype, id='friends.p%d' % i, sha256='%064x' % (i + 1),
                                    runtime_dependencies=dependency))
            index['packages'] = entries
        self.replace_index(change)
        self.lock['roots'] = ['%064x' % 1]
        self.lock['packages'] = ['%064x' % i for i in range(65, 0, -1)]
        self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(False)

    def test_package_growth_rejected_with_captured_size(self):
        initial_size = self.base.stat().st_size
        self.assertEqual(verify_package(self.base)['archive_size'], initial_size)
        changed = False
        def grow(event, item, data):
            nonlocal changed
            if not changed:
                changed = True
                with self.base.open('ab') as stream:
                    stream.write(bytes(4096))
        with self.assertRaises(PackageError):
            verify_package(self.base, sink=grow)

    def test_fifo_package_rejected_without_blocking(self):
        fifo = self.folder / 'input.xpk'
        os.mkfifo(fifo)
        code = ('import sys; sys.path.insert(0,sys.argv[1]); '
                'from xypm_format import verify_package; verify_package(sys.argv[2])')
        result = subprocess.run([sys.executable, '-c', code, str(root / 'scripts'), str(fifo)],
                                capture_output=True, text=True, timeout=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('regular non-symlink', result.stderr)

    def test_selected_package_upgrade(self):
        image = self.folder / 'empty.img'; image.write_bytes(make_image())
        first, upgraded = self.folder / 'first.img', self.folder / 'upgraded.img'
        transact_locked(self.repository, self.lock_path, 'friends.base', image, first, profile, 'install')
        package = self.package('friends.base', revision=1)
        replacement = self.folder / 'replacement'
        create_repository([package], replacement, profile)
        lock = self.folder / 'upgrade_lock.json'
        write_metadata(lock, make_lock(replacement, [sha_file(package)], profile))
        transact_locked(replacement, lock, 'friends.base', first, upgraded, profile, 'upgrade')
        self.assertEqual(query_image(upgraded, profile, 'info', 'friends.base')['manifest']['revision'], 1)

    def test_many_payload_members_binary_lookup(self):
        package = self.package('friends.large', members=1024)
        replacement = self.folder / 'replacement'
        create_repository([package], replacement, profile)
        shutil.rmtree(self.repository); replacement.rename(self.repository)
        self.lock = make_lock(self.repository, [sha_file(package)], profile)
        self.lock_path.write_bytes(canonical(self.lock))
        self.check_both(True)

    def test_native_captured_size_and_extra_tail(self):
        size = self.base.stat().st_size
        for reported, expected in ((size, 0), (size - 512, 3), (size + 512, 3)):
            with self.subTest(reported=reported):
                result = subprocess.run([str(native_binary), '--size', str(self.base), str(reported)],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_xypm_build_preparation_version_and_source_closure(self):
        import build_xypm
        fixture_root = self.folder / 'builder'
        inputs = ['src/user/programs/' + name for name in (
            'xypm.cpp', 'xypm_native.hpp', 'xypm_journal.hpp', 'xypm_transaction_impl.hpp',
            'xypm_recover.cpp', 'xypm_repository.hpp', 'xypm_repository_io.hpp')]
        inputs += ['src/user/include/xos/text.hpp', 'src/user/include/xos/unicode_width_data.hpp',
                   'scripts/xos_app.py']
        for relative in inputs:
            destination = fixture_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, destination)
        prepared = []
        def inspect_project(project, sdk, selected_profile):
            app = load_json(project / 'xos_app.json')
            prepared.append(app)
            self.assertEqual((app['id'], app['upstream_version'], app['revision']), ('xos.xypm', '0.4.0', 0))
            files = {item['source'] for item in app['files']}
            for name in ('xypm_repository.hpp', 'xypm_repository_io.hpp'):
                self.assertIn('src/' + name, files)
                self.assertEqual((project / 'src' / name).read_bytes(), (root / 'src/user/programs' / name).read_bytes())
            return {'output': 'build/xypm.elf'}
        with mock.patch.object(build_xypm, 'ROOT', fixture_root), \
             mock.patch.object(build_xypm, 'build', side_effect=inspect_project), \
             mock.patch.object(build_xypm, 'pack', return_value={'sha256': '0' * 64}), \
             mock.patch.object(sys, 'argv', ['build_xypm.py', '--sdk', str(self.folder), '--profile', str(DEFAULT_PROFILE)]), \
             contextlib.redirect_stdout(io.StringIO()):
            build_xypm.main()
        self.assertEqual(len(prepared), 1)

    def test_cli_round_trip(self):
        command = [sys.executable, str(root / 'scripts/xypm.py'), 'repo-verify',
                   str(self.repository), str(self.lock_path), '--lock-sha256', sha_file(self.lock_path)]
        output = subprocess.check_output(command, text=True)
        self.assertEqual(len(json.loads(output)['packages']), 2)

    def test_single_package_transactions_and_reverse_dependency(self):
        image = self.folder / 'empty.img'; image.write_bytes(make_image())
        original = sha_file(image)
        first, second, removed = (self.folder / name for name in ('first.img', 'second.img', 'removed.img'))
        with self.assertRaises(PackageError):
            transact_locked(self.repository, self.lock_path, 'friends.app', image, first, profile, 'install')
        self.assertFalse(first.exists()); self.assertEqual(sha_file(image), original)
        transact_locked(self.repository, self.lock_path, 'friends.base', image, first, profile, 'install')
        transact_locked(self.repository, self.lock_path, 'friends.app', first, second, profile, 'install')
        self.assertEqual(len(query_image(second, profile)['packages']), 2)
        with self.assertRaises(PackageError):
            transact(second, removed, profile, 'remove', package_id='friends.base')
        self.assertFalse(removed.exists())
        transact(second, removed, profile, 'remove', package_id='friends.app')
        self.assertEqual(len(query_image(removed, profile)['packages']), 1)
        self.assertEqual(sha_file(image), original)

    def test_package_replacement_between_verify_and_stage(self):
        import xypm_repository as module
        original = module.verify_repository
        image = self.folder / 'empty.img'; image.write_bytes(make_image())
        before = sha_file(image); output = self.folder / 'result.img'
        def replace(*args, **kwargs):
            result = original(*args, **kwargs)
            shutil.copyfile(self.application, self.repository / (self.base_hash + '.xpk'))
            return result
        module.verify_repository = replace
        try:
            with self.assertRaises(PackageError):
                transact_locked(self.repository, self.lock_path, 'friends.base', image, output, profile, 'install')
        finally:
            module.verify_repository = original
        self.assertFalse(output.exists()); self.assertEqual(sha_file(image), before)


def main():
    global native_binary
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    arguments = parser.parse_args()
    output = root / 'build/package_p3'
    output.mkdir(parents=True, exist_ok=True)
    feature_rows = ''.join('!__builtin_strcmp(name,%s)||' % json.dumps(name) for name in profile['features'])
    (output / 'xypm_profile.hpp').write_text(
        '#define XYP_PACKAGE_PROFILE_ID %s\n' % json.dumps(profile['id']) +
        'static inline bool xypm_profile_feature(const char* name) { return %sfalse; }\n' % feature_rows +
        '#define XYP_PACKAGE_FEATURES(name) xypm_profile_feature(name)\n')
    native_binary = output / ('repository_sanitized' if arguments.sanitize else 'repository_native')
    command = [shutil.which('c++') or 'c++', '-std=c++17', '-O1', '-g', '-fno-omit-frame-pointer',
               '-I' + str(root / 'src/user/include'), '-I' + str(root / 'src/shared/include'),
               '-I' + str(output), str(root / 'tests/fixtures/xypm_json/repository_cases.cpp'),
               '-o', str(native_binary)]
    if arguments.sanitize:
        command[1:1] = ['-fsanitize=address,undefined', '-no-pie']
    subprocess.run(command, check=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(repository_cases)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sources = ('scripts/xypm_repository.py', 'scripts/xypm.py', 'scripts/xypm_format.py',
               'scripts/xypm_image.py', 'scripts/build_xypm.py', 'src/user/programs/xypm.cpp',
               'src/user/programs/xypm_repository.hpp', 'src/user/programs/xypm_repository_io.hpp',
               'src/user/programs/xypm_native.hpp', 'tests/package_p3_repository.py',
               'tests/fixtures/xypm_json/repository_cases.cpp')
    report = {'status': 'passed' if result.wasSuccessful() else 'failed', 'tests': result.testsRun,
              'sanitizers': arguments.sanitize, 'guest': 'not_run', 'shared_cases': case_results,
              'asan_options': os.environ.get('ASAN_OPTIONS', ''),
              'source_sha256': {path: sha_file(root / path) for path in sources},
              'native_binary_sha256': sha_file(native_binary),
              'compiler': subprocess.check_output([command[0], '--version'], text=True).splitlines()[0]}
    (output / ('sanitized_report.json' if arguments.sanitize else 'report.json')).write_bytes(canonical(report))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
