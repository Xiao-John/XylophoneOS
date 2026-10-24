# SPDX-License-Identifier: Apache-2.0
"""Hash/role and search-order checks for the C++ install contract, not guest tests."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cpp_seed_bundle import bind_runtime, cpp_specs, FEATURES
from build_cpp_abi_probe import checked_hash, ManifestError
from prepare_gcc_seed import SPECS


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def directory_digest(path):
    value = hashlib.sha256()
    for item in sorted(path.rglob('*')):
        if item.is_file():
            value.update(item.relative_to(path).as_posix().encode())
            value.update(b'\0')
            value.update(bytes.fromhex(digest(item)))
    return value.hexdigest()


class BundleCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.sdk, self.runtime = self.root / 'sdk', self.root / 'runtime'
        for path in (self.sdk / 'include', self.runtime / 'include', self.runtime / 'lib'):
            path.mkdir(parents=True)
        for name in ('manifest.json', 'crt0_posix.o', 'user.ld'):
            (self.sdk / name).write_text(name)
        (self.runtime / 'include/string').write_text('hash-only fixture; never compiled')
        for name in ('libstdc++', 'libsupc++', 'libgcc'):
            (self.runtime / 'lib' / (name + '.a')).write_bytes(b'!<arch>\n')
        self.manifest = self.root / 'runtime.json'
        self.data = {'runtime_kind': 'target_application_runtime', 'target_triple': 'x86_64-elf',
                     'runtime_build_flags': [],
                     'features': {name: {'status': 'ready'} for name in FEATURES},
                     'sdk_manifest': {'path': 'manifest.json', 'sha256': digest(self.sdk / 'manifest.json')},
                     'crt': self.artifact('sdk', 'crt0_posix.o'),
                     'linker_script': self.artifact('sdk', 'user.ld'),
                     'include_dirs': [{'root': 'runtime', 'path': 'include',
                                       'sha256': directory_digest(self.runtime / 'include')}],
                     'archives': [dict(self.artifact('runtime', 'lib/' + name + '.a'), role=name)
                                  for name in ('libstdc++', 'libsupc++', 'libgcc')]}

    def artifact(self, root, name):
        path = (self.sdk if root == 'sdk' else self.runtime) / name
        return {'root': root, 'path': name, 'sha256': digest(path)}

    def bind(self):
        self.manifest.write_text(json.dumps(self.data))
        return bind_runtime(self.manifest, self.runtime, self.sdk,
                            lambda path, guest: {'path': str(path), 'guest_path': guest, 'sha256': digest(path)})

    def test_target_binding_and_cpp_header_order(self):
        files, includes, archives = self.bind()
        self.assertEqual(len(files), 4)
        self.assertIn('/sysroot/lib/libstdc++.a', [item['guest_path'] for item in files])
        specs = cpp_specs(SPECS, includes, archives)
        cpp = specs.split('*cc1plus:\n')[1]
        self.assertIn('-isystem /sysroot/cxx_include/0', cpp)
        self.assertIn('-idirafter /sysroot/include', specs)
        self.assertNotIn('-isystem /sysroot/include', specs)
        self.assertIn('-ftls-model=local-exec', cpp)
        self.assertIn('--start-group -lstdc++ -lsupc++', specs)
        self.assertNotIn('collect2', specs)

    def test_host_runtime_rejected(self):
        self.data['runtime_kind'] = 'host_compiler_runtime'
        with self.assertRaisesRegex(ValueError, 'target_application_runtime'):
            self.bind()

    def test_disabled_exception_or_rtti_rejected(self):
        for flag in ('-fno-exceptions', '-fno-rtti'):
            with self.subTest(flag=flag):
                self.data['runtime_build_flags'] = [flag]
                with self.assertRaisesRegex(ValueError, 'retain exceptions'):
                    self.bind()

    def test_modified_archive_is_not_accepted(self):
        (self.runtime / 'lib/libsupc++.a').write_bytes(b'changed')
        with self.assertRaisesRegex(ManifestError, 'sha256 mismatch'):
            self.bind()

    def test_incomplete_feature_or_archive_is_not_accepted(self):
        self.data['features']['tls_destructors']['status'] = 'not_ready'
        with self.assertRaisesRegex(ValueError, 'tls_destructors'):
            self.bind()
        self.data['features']['tls_destructors']['status'] = 'ready'
        self.data['archives'].pop()
        with self.assertRaisesRegex(ValueError, 'actual libgcc'):
            self.bind()


if __name__ == '__main__':
    unittest.main()
