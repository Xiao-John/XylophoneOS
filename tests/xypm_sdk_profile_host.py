#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise SDK/profile admission using explicit synthetic host-only materials."""
from pathlib import Path
import argparse
import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import xypm_sdk_profile as module
from xypm_format import PackageError, canonical, load_json, sha_file


def object_bytes(machine=62, symbols=(), weak=False):
    result = bytearray(64)
    result[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', result, 16, 1, machine, 1)
    if symbols:
        names = b'\0'
        table = bytes(24)
        for name in sorted(symbols):
            table += struct.pack('<IBBHQQ', len(names), (2 if weak else 1) << 4, 0, 0, 0, 0)
            names += name.encode() + b'\0'
        string_offset = len(result)
        result += names
        symbol_offset = len(result)
        result += table
        struct.pack_into('<Q', result, 40, len(result))
        struct.pack_into('<HH', result, 58, 64, 3)
        result += bytes(64)
        result += struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, string_offset, len(names), 0, 0, 1, 0)
        result += struct.pack('<IIQQQQIIQQ', 0, 2, 0, 0, symbol_offset, len(table), 1, 1, 8, 24)
    return bytes(result)


def archive_map_bytes(members):
    names = b''
    offsets = {}
    for name in members:
        offsets[name] = len(names)
        names += name.encode() + b'/\n'
    records = [('//', names)] + [('/' + str(offsets[name]), data) for name, data in members.items()]
    result = b'!<arch>\n'
    for name, data in records:
        header = (name.ljust(16) + '0           ' + '0     ' + '0     '
                  + '644     ' + str(len(data)).ljust(10) + '`\n').encode()
        assert len(header) == 60
        result += header + data + (b'\n' if len(data) % 2 else b'')
    return result


def archive_bytes(machine=62):
    return archive_map_bytes({'fixture.o': object_bytes(machine)})


def put(root, name, data=b'synthetic host fixture\n'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


class profile_cases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='xypm_profile_')
        self.root = Path(self.temp.name)
        self.newlib = self.root / 'newlib'
        self.glibc = self.root / 'glibc'
        self.sysroot = self.glibc / 'sysroot'
        for name in ['lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a',
                     'cpp/lib/libgcc.a', 'cpp/lib/libstdc++.a', 'cpp/lib/libsupc++.a']:
            put(self.newlib, name, archive_bytes())
        put(self.newlib, 'crt0_posix.o', object_bytes())
        put(self.newlib, 'user.ld', b'OUTPUT_FORMAT(elf64-x86-64)\nENTRY(_start)\n')
        put(self.newlib, 'include/_newlib_version.h', b'#define _NEWLIB_VERSION "4.6.0"\n')
        for name in ['LICENSE', 'NOTICE', 'COPYING.NEWLIB', 'cpp/include/c++/16.2.0/vector',
                     'cpp/include/c++/16.2.0/x86_64-unknown-elf/bits/c++config.h']:
            put(self.newlib, name)
        self.nmeta = {'abi': 1, 'target': 'x86_64-elf', 'runtime_model': 'single',
                      'build_id': '1234567890abcdef',
                      'libc': {'name': 'newlib', 'version': '4.6.0.20260123',
                               'libc_sha256': sha_file(self.newlib / 'lib/libc.a'),
                               'libm_sha256': sha_file(self.newlib / 'lib/libm.a')},
                      'process_extensions': {'startup_versions': [1, 2, 3]}}
        lineage = {'libc': self.nmeta['libc'], 'cpp_archives': {name: sha_file(self.newlib / 'cpp/lib' / name)
                   for name in ['libstdc++.a', 'libsupc++.a', 'libgcc.a']}}
        put(self.newlib, 'xypm_sdk_lineage.json', canonical(lineage))
        self.save_newlib()
        for name in ['libc.a', 'libm.a', 'libgcc.a', 'libstdc++.a', 'libsupc++.a']:
            put(self.sysroot, 'usr/lib/' + name, archive_bytes())
        for name in module.GLIBC_CRT:
            put(self.sysroot, 'usr/lib/' + name, object_bytes())
        put(self.sysroot, 'user.ld', b'OUTPUT_FORMAT(elf64-x86-64)\nENTRY(_start)\n')
        put(self.sysroot, 'usr/include/features.h', b'#define __GLIBC__ 2\n#define __GLIBC_MINOR__ 44\n')
        for name in ['usr/lib/compiler-include/stddef.h', 'usr/share/xos-glibc/COPYING.LIB',
                     'usr/share/xos-glibc/LICENSES', 'usr/include/c++/16.2.0/vector',
                     'usr/include/c++/16.2.0/x86_64-unknown-xos/bits/c++config.h',
                     'usr/share/xos-glibc/cxx/licenses/COPYING3',
                     'usr/share/xos-glibc/cxx/licenses/COPYING.RUNTIME']:
            put(self.sysroot, name)
        tool = {'available': True, 'version_exit_code': 0, 'version': 'GCC 16.2.0', 'sha256': 'c' * 64}
        self.gmeta = {'status': 'static_sdk_built', 'profile': 'xos_glibc_static_research_v1',
                      'runtime_family': 'glibc', 'stub_functions': ['opendir', 'execve'],
                      'tools': {'x86_64-elf-gcc': tool, 'x86_64-elf-g++': tool}}
        self.authentication()
        self.authentication(cxx=True)
        self.gmeta['source_sha256'] = 'a' * 64
        self.gmeta['cxx_runtime'] = {'status': 'built', 'gcc_version': '16.2.0',
             'target': 'x86_64-unknown-xos', 'thread_model': 'posix', 'locale_model': 'generic',
             'source_sha256': 'a' * 64,
             'include_directories': ['usr/include/c++/16.2.0',
                 'usr/include/c++/16.2.0/x86_64-unknown-xos', 'usr/include/c++/16.2.0/backward']}
        unwinder_members = {name: object_bytes(symbols=module.GLIBC_UNWINDER_SYMBOLS)
                            for name in sorted(module.GLIBC_UNWINDER_MEMBERS)}
        put(self.sysroot, 'usr/lib/libgcc.a', archive_map_bytes(unwinder_members))
        self.gmeta['cxx_runtime']['unwinder'] = {'thread_model': 'posix', 'frame_registry': 'pthread_mutex',
            'replaced_members': {name: hashlib.sha256(data).hexdigest() for name, data in unwinder_members.items()}}
        self.save_glibc()

    def tearDown(self):
        self.temp.cleanup()

    def authentication(self, cxx=False):
        prefix = 'cxx_' if cxx else ''
        directory = self.glibc / ('gcc_source_verification' if cxx else 'source_verification')
        materials = self.sysroot / ('usr/share/xos-glibc/cxx/port' if cxx else 'usr/share/xos-glibc/port')
        key = put(materials, 'keys/release.asc')
        signature = put(materials, 'keys/release.sig')
        trust = {'primary_fingerprint': 'A' * 40, 'signing_fingerprint': 'B' * 40,
                 'key_file': 'keys/release.asc', 'signature_file': 'keys/release.sig',
                 'key_sha256': sha_file(key)}
        lock = {'version': '16.2.0' if cxx else '2.44', 'signer_trust': trust,
                'sha256' if cxx else 'archive_sha256': 'a' * 64,
                'signature_sha256': sha_file(signature)}
        lock_file = put(materials, 'source_lock.json', canonical(lock))
        evidence = {name: sha_file(put(directory, name)) for name in ['gpgv.log', 'release_key.gpg']}
        status = ('[GNUPG:] GOODSIG ' + 'B' * 16 + ' Synthetic fixture\n[GNUPG:] VALIDSIG '
                  + 'B' * 40 + ' 2026-01-01 1 0 4 0 1 8 00 ' + 'A' * 40 + '\n').encode()
        evidence['gpgv.status'] = sha_file(put(directory, 'gpgv.status', status))
        record = {'status': 'upstream_signature_verified', 'gpgv_exit': 0,
                  'lock_sha256': sha_file(lock_file), 'archive_sha256': 'a' * 64,
                  'key_sha256': sha_file(key), 'signature_sha256': sha_file(signature),
                  'trust_record': trust, 'signature': {name: trust[name]
                     for name in ['primary_fingerprint', 'signing_fingerprint']} | {
                         'signature_timestamp': 1, 'hash_algorithm': 8}, 'evidence': evidence}
        report = put(directory, 'report.json', canonical(record))
        self.gmeta[prefix + 'source_verification'] = record
        self.gmeta[prefix + 'source_verification_report_sha256'] = sha_file(report)

    def save_newlib(self):
        put(self.newlib, 'manifest.json', canonical(self.nmeta))

    def save_glibc(self):
        self.gmeta['artifacts'] = module.sdk_snapshot(self.sysroot)[1]
        put(self.glibc, 'manifest.json', canonical(self.gmeta))

    def create(self, family='glibc', cxx=False, features=()):
        return module.candidate_profile(family, getattr(self, family),
                                        'xos-x86_64-' + family + '-test-v1', cxx=cxx, features=features)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/create_xypm_profile.py'), *map(str, args)],
                              capture_output=True, text=True)

    def test_newlib_and_glibc_candidates_verify_without_guest_claim(self):
        for family in ['newlib', 'glibc']:
            profile = self.create(family, cxx=True)
            self.assertEqual(profile['verified_system_builds'], [])
            self.assertEqual(profile['status'], 'candidate_guest_not_run')
            result = module.verify_profile(profile, family, getattr(self, family))
            self.assertEqual(result['status'], 'candidate_binding_verified')
            self.assertEqual(result['guest_qualification'], 'not_run')

    def test_wrong_family_rejected(self):
        for family, source in [('newlib', self.glibc), ('glibc', self.newlib)]:
            with self.assertRaisesRegex(PackageError, 'family mismatch'):
                module.candidate_profile(family, source, 'xos-x86_64-' + family + '-test-v1')

    def test_newlib_missing_build_id_rejected(self):
        self.nmeta.pop('build_id')
        self.save_newlib()
        with self.assertRaisesRegex(PackageError, 'build_id'):
            self.create('newlib')

    def test_newlib_malformed_build_id_rejected(self):
        for value in (None, True, 1234, '', '1234567890ABCDEF', '0123', 'g' * 16):
            with self.subTest(build_id=value):
                self.nmeta['build_id'] = value
                self.save_newlib()
                with self.assertRaisesRegex(PackageError, 'build_id'):
                    self.create('newlib')

    def test_newlib_builder_rejects_glibc_profile_before_access(self):
        from xos_app import sdk_check
        with self.assertRaisesRegex(PackageError, 'requires the newlib runtime family'):
            sdk_check(self.newlib, self.create())

    def test_cli_rejects_nonobject_manifest_without_traceback(self):
        put(self.glibc, 'manifest.json', b'[]\n')
        output = self.root / 'candidate.json'
        result = self.cli('create', '--runtime-family', 'glibc', '--sdk-build', self.glibc,
                          '--id', 'xos-x86_64-glibc-test-v1', '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('metadata object required: manifest.json', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertFalse(output.exists())

    def test_nested_metadata_objects_rejected(self):
        cases = [('newlib', self.nmeta, 'libc'),
                 ('newlib', self.nmeta, 'archive_provenance'),
                 ('newlib', self.nmeta, 'process_extensions'),
                 ('glibc', self.gmeta, 'tools'),
                 ('glibc', self.gmeta, 'cxx_runtime')]
        for family, metadata, name in cases:
            with self.subTest(family=family, field=name):
                saved = metadata.get(name, {})
                metadata[name] = []
                self.save_newlib() if family == 'newlib' else self.save_glibc()
                with self.assertRaisesRegex(PackageError, 'metadata object required: ' + name):
                    self.create(family, cxx=True)
                metadata[name] = saved
                self.save_newlib() if family == 'newlib' else self.save_glibc()

    def test_boolean_compiler_exit_status_rejected(self):
        self.gmeta['tools']['x86_64-elf-gcc']['version_exit_code'] = False
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'compiler identity/version mismatch'):
            self.create()

    def test_candidate_id_contains_family(self):
        with self.assertRaisesRegex(PackageError, 'runtime family prefix'):
            module.candidate_profile('glibc', self.glibc, 'xos-x86_64-newlib-test-v1')

    def test_registered_id_cannot_be_rebound_but_can_be_verified(self):
        profile = self.create()
        put(self.root, 'config/package/registered.json', canonical(profile))
        with mock.patch.object(module, 'ROOT', self.root):
            with self.assertRaisesRegex(PackageError, 'frozen profile id'):
                self.create()
            module.verify_profile(profile, 'glibc', self.glibc)

    def test_sdk_manifest_changed_after_generation(self):
        profile = self.create()
        self.gmeta['extra_build_input'] = 'different'
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'complete SDK binding'):
            module.verify_profile(profile, 'glibc', self.glibc)

    def test_sdk_artifact_changed_after_generation(self):
        profile = self.create()
        put(self.sysroot, 'user.ld', b'changed')
        with self.assertRaisesRegex(PackageError, 'digest mismatch'):
            module.verify_profile(profile, 'glibc', self.glibc)

    def test_extra_unlisted_header_rejected(self):
        put(self.sysroot, 'usr/include/injected.h')
        with self.assertRaisesRegex(PackageError, 'artifact set differs'):
            self.create()

    def test_manifest_path_escape_rejected(self):
        self.gmeta['artifacts']['../outside'] = 'f' * 64
        put(self.glibc, 'manifest.json', canonical(self.gmeta))
        with self.assertRaisesRegex(PackageError, 'canonical and confined'):
            self.create()

    def test_symlink_and_special_entries_rejected(self):
        link = self.sysroot / 'usr/include/link.h'
        link.symlink_to('features.h')
        with self.assertRaisesRegex(PackageError, 'nonregular entry'):
            self.create()

    def test_sysroot_symlink_rejected(self):
        real = self.glibc / 'real_sysroot'
        self.sysroot.rename(real)
        self.sysroot.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(PackageError, 'real directory'):
            self.create()

    def test_mixed_target_archive_rejected_after_rehash(self):
        put(self.sysroot, 'usr/lib/libgcc.a', archive_bytes(machine=183))
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'object target mismatch'):
            self.create()

    def test_glibc_terminal_archive_is_bound_and_target_checked(self):
        name = 'usr/lib/libxos_terminal.a'
        archive = put(self.sysroot, name, archive_bytes())
        self.save_glibc()
        binding = self.create()['sdk_binding']
        self.assertEqual(binding['link_artifacts'][name], sha_file(archive))
        self.assertEqual(binding['archive_members'][name], 1)
        archive.write_bytes(archive_bytes(machine=183))
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'object target mismatch'):
            self.create()

    def test_missing_crt_rejected_after_rehash(self):
        (self.sysroot / 'usr/lib/crtend.o').unlink()
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'SDK file missing'):
            self.create()

    def test_header_version_mismatch_rejected_after_rehash(self):
        put(self.sysroot, 'usr/include/features.h', b'#define __GLIBC__ 2\n#define __GLIBC_MINOR__ 43\n')
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'header/source version mismatch'):
            self.create()

    def test_missing_source_authentication_rejected(self):
        self.gmeta['source_verification']['status'] = 'not_run'
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'source authentication missing'):
            self.create()

    def test_authentication_evidence_tamper_rejected(self):
        put(self.glibc, 'source_verification/gpgv.status', b'tampered')
        with self.assertRaisesRegex(PackageError, 'digest mismatch'):
            self.create()

    def test_expired_signature_status_rejected_even_after_rehash(self):
        directory = self.glibc / 'source_verification'
        with (directory / 'gpgv.status').open('ab') as stream:
            stream.write(b'[GNUPG:] EXPKEYSIG synthetic\n')
        record = self.gmeta['source_verification']
        record['evidence']['gpgv.status'] = sha_file(directory / 'gpgv.status')
        put(directory, 'report.json', canonical(record))
        self.gmeta['source_verification_report_sha256'] = sha_file(directory / 'report.json')
        self.save_glibc()
        with self.assertRaisesRegex(ValueError, 'release signature rejected'):
            self.create()

    def test_cxx_authentication_separate_from_glibc(self):
        del self.gmeta['cxx_source_verification_report_sha256']
        self.save_glibc()
        self.create(cxx=False)
        with self.assertRaisesRegex(PackageError, 'invalid SHA-256'):
            self.create(cxx=True)

    def test_cxx_wrong_thread_model_rejected(self):
        self.gmeta['cxx_runtime']['thread_model'] = 'single'
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'identity/model mismatch'):
            self.create(cxx=True)

    def test_cxx_single_thread_unwinder_rejected(self):
        self.gmeta['cxx_runtime']['unwinder']['thread_model'] = 'single'
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'unwinder thread model mismatch'):
            self.create(cxx=True)

    def test_cxx_separate_unwinder_requires_its_own_profile(self):
        put(self.sysroot, 'usr/lib/libgcc_eh.a', archive_bytes())
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'separate unwind archive needs a matching profile'):
            self.create(cxx=True)

    def test_cxx_unwinder_member_changed_after_rehash_rejected(self):
        members = {name: object_bytes() for name in sorted(module.GLIBC_UNWINDER_MEMBERS)}
        members['unwind-dw2-fde.o'] += b'different unwinder'
        put(self.sysroot, 'usr/lib/libgcc.a', archive_map_bytes(members))
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'archive member digest mismatch'):
            self.create(cxx=True)

    def test_cxx_weak_pthread_unwinder_rejected_after_rehash(self):
        members = {name: object_bytes(symbols=module.GLIBC_UNWINDER_SYMBOLS, weak=True)
                   for name in sorted(module.GLIBC_UNWINDER_MEMBERS)}
        put(self.sysroot, 'usr/lib/libgcc.a', archive_map_bytes(members))
        self.gmeta['cxx_runtime']['unwinder']['replaced_members'] = {
            name: hashlib.sha256(data).hexdigest() for name, data in members.items()}
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'lacks strong pthread dependencies'):
            self.create(cxx=True)

    def test_cxx_header_path_escape_rejected(self):
        self.gmeta['cxx_runtime']['include_directories'][0] = '../newlib/include'
        self.save_glibc()
        with self.assertRaisesRegex(PackageError, 'include layout mismatch'):
            self.create(cxx=True)

    def test_newlib_libc_digest_rejected(self):
        self.nmeta['libc']['libc_sha256'] = 'f' * 64
        self.save_newlib()
        with self.assertRaisesRegex(PackageError, 'digest mismatch'):
            self.create('newlib')

    def test_newlib_cxx_lineage_rejected(self):
        lineage = load_json(self.newlib / 'xypm_sdk_lineage.json')
        lineage['libc']['version'] = '2.44'
        put(self.newlib, 'xypm_sdk_lineage.json', canonical(lineage))
        with self.assertRaisesRegex(PackageError, 'lineage libc mismatch'):
            self.create('newlib', cxx=True)

    def test_stub_feature_rejected(self):
        with self.assertRaisesRegex(PackageError, 'feature still has stubs'):
            self.create(features=['directories'])

    def test_claimed_guest_build_rejected(self):
        profile = self.create()
        profile['verified_system_builds'] = ['unexecuted']
        with self.assertRaisesRegex(PackageError, 'complete SDK binding'):
            module.verify_profile(profile, 'glibc', self.glibc)

    def test_boolean_protocol_version_rejected(self):
        profile = self.create()
        profile['format_version'] = True
        with self.assertRaisesRegex(PackageError, 'complete SDK binding'):
            module.verify_profile(profile, 'glibc', self.glibc)

    def test_sdk_mutation_during_validation_rejected(self):
        original = module.newlib_binding
        def changing(*args):
            result = original(*args)
            put(self.newlib, 'include/new_header.h')
            return result
        with mock.patch.object(module, 'newlib_binding', changing):
            with self.assertRaisesRegex(PackageError, 'changed during profile validation'):
                self.create('newlib')

    def test_external_source_evidence_mutation_during_validation_rejected(self):
        original = module.glibc_binding
        def changing(*args):
            result = original(*args)
            put(self.glibc, 'source_verification/gpgv.log', b'changed during SDK validation')
            return result
        with mock.patch.object(module, 'glibc_binding', changing):
            with self.assertRaisesRegex(PackageError, 'source evidence after validation'):
                self.create()

    def test_cli_creation_and_verification(self):
        output = self.root / 'profiles/glibc.json'
        args = ['--runtime-family', 'glibc', '--sdk-build', self.glibc]
        created = self.cli('create', *args, '--id', 'xos-x86_64-glibc-test-v1', '--output', output)
        self.assertEqual(created.returncode, 0, created.stderr)
        verified = self.cli('verify', *args, '--profile', output)
        self.assertEqual(verified.returncode, 0, verified.stderr)

    def test_cli_preserves_existing_output(self):
        output = put(self.root, 'existing.json', b'existing evidence')
        result = self.cli('create', '--runtime-family', 'glibc', '--sdk-build', self.glibc,
                          '--id', 'xos-x86_64-glibc-test-v1', '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), b'existing evidence')

    def test_cli_rejects_output_inside_sdk(self):
        result = self.cli('create', '--runtime-family', 'glibc', '--sdk-build', self.glibc,
                          '--id', 'xos-x86_64-glibc-test-v1', '--output', self.glibc / 'profile.json')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.glibc / 'profile.json').exists())

    def test_cli_rejects_symlinked_sdk_root(self):
        link = self.root / 'sdk_link'
        link.symlink_to(self.glibc, target_is_directory=True)
        output = self.root / 'candidate.json'
        result = self.cli('create', '--runtime-family', 'glibc', '--sdk-build', link,
                          '--id', 'xos-x86_64-glibc-test-v1', '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_cli_failure_leaves_no_profile(self):
        self.gmeta['status'] = 'building'
        self.save_glibc()
        output = self.root / 'new/profile.json'
        result = self.cli('create', '--runtime-family', 'glibc', '--sdk-build', self.glibc,
                          '--id', 'xos-x86_64-glibc-test-v1', '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_glibc_builder_rejects_newlib_profile(self):
        profile = module.candidate_profile('newlib', self.newlib, 'xos-x86_64-newlib-test-v1', cxx=True)
        self.check_glibc_build_rejection(profile, 'profile runtime family mismatch')

    def test_glibc_builder_rejects_c_only_profile_for_cpp(self):
        self.check_glibc_build_rejection(self.create(cxx=False), 'candidate cxx_runtime feature')

    def check_glibc_build_rejection(self, profile, message):
        profile_path = put(self.root, 'program-profile.json', canonical(profile))
        source = ROOT / 'tests/fixtures/xypm/glibc_profile_program.cpp'
        output = self.root / 'program.elf'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_glibc_program.py'),
                                 '--sdk', str(self.sysroot), '--profile', str(profile_path), '--cxx',
                                 '--source', str(source), '--output', str(output)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.elf.build').exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/xypm_profiles_host')
    args = parser.parse_args()
    source_names = ('scripts/create_xypm_profile.py', 'scripts/xypm_sdk_profile.py', 'scripts/build_glibc_program.py',
                    'scripts/xos_app.py', 'tests/xypm_sdk_profile_host.py')
    source_inputs = {name: sha_file(ROOT / name) for name in source_names}
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(profile_cases)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    inputs_unchanged = source_inputs == {name: sha_file(ROOT / name) for name in source_names}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'status': 'passed' if result.wasSuccessful() and inputs_unchanged else 'failed', 'tests': result.testsRun,
              'scope': 'synthetic host-only SDK admission fixtures; no upstream signature or guest execution',
              'guest': 'not_run', 'sources': source_inputs, 'inputs_unchanged': inputs_unchanged}
    (output / 'report.json').write_bytes(canonical(report))
    raise SystemExit(0 if result.wasSuccessful() and inputs_unchanged else 1)
