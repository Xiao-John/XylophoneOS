# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

from archive_member_map import read_archive
from build_glibc_sdk import inputs, sha
from glibc_g1_probe import tool_identity
from verify_glibc_source import check_status
from xypm_sdk_profile import (GLIBC_UNWINDER_MEMBERS, GLIBC_UNWINDER_SYMBOLS,
                              inspect_sdk, sdk_snapshot, strong_undefined_symbols)

root = Path.cwd()
work = root / 'build/qualified'
c_sdk = work / 'sdk_c'
cxx = work / 'cxx'
output = work / 'sdk_cxx'
old = Path(sys.argv[1])
old_port = old / 'sysroot/usr/share/xos-glibc/cxx/port'
lock_path = old_port / 'source_lock.json'
assert sha(lock_path) == '3fbd5444abe4946667813ea45c66c2a1bd1bf43e937d142c4ca8bea735e1e28f'
lock = json.loads(lock_path.read_text())
trust = lock['signer_trust']
archive = cxx / 'material' / lock['source_archive']
signature = cxx / 'material' / Path(trust['signature_file']).name
key = cxx / 'material' / Path(trust['key_file']).name
assert sha(archive) == lock['sha256'] and sha(signature) == lock['signature_sha256']
assert sha(key) == trust['key_sha256']
assert json.loads((root / 'src/ports/gcc/source_lock.json').read_text())['sha256'] == lock['sha256']

c_metadata = json.loads((c_sdk / 'manifest.json').read_text())
c_binding = inspect_sdk('glibc', c_sdk, features=('directories', 'stdio_transfer', 'threads'))['binding']
assert c_metadata['status'] == 'static_sdk_built' and c_metadata['inputs'] == inputs()
for name in ('x86_64-elf-gcc', 'x86_64-elf-g++', 'x86_64-elf-as', 'x86_64-elf-ld', 'x86_64-elf-ar',
             'x86_64-elf-ranlib'):
    assert tool_identity(name)['sha256'] == c_metadata['tools'][name]['sha256'], name
c_header = c_sdk / 'sysroot/usr/include/pthread.h'
self_declaration, = re.findall(r'^extern pthread_t pthread_self[^;]+;', c_header.read_text(), flags=re.MULTILINE)
assert '__const__' not in self_declaration and 'const' not in self_declaration

output.mkdir()
sysroot = output / 'sysroot'
shutil.copytree(c_sdk / 'sysroot', sysroot)
shutil.copytree(c_sdk / 'source_verification', output / 'source_verification', ignore=shutil.ignore_patterns('gnupg'))
verification = output / 'gcc_source_verification'
verification.mkdir()
for name in ('gpgv.status', 'gpgv.log'):
    shutil.copyfile(cxx / 'logs' / name, verification / name)
shutil.copyfile(key, verification / 'release_key.gpg')
verified_signature = check_status(0, (verification / 'gpgv.status').read_text(), trust)
verification_record = {
    'schema': 1, 'status': 'upstream_signature_verified', 'gpgv_exit': 0,
    'verified_at': datetime.fromtimestamp((cxx / 'logs/gpgv.status').stat().st_mtime, timezone.utc).isoformat(),
    'archive_sha256': sha(archive), 'signature_sha256': sha(signature), 'key_sha256': sha(key),
    'lock_sha256': sha(lock_path), 'signature': verified_signature, 'trust_record': trust,
    'evidence': {name: sha(verification / name) for name in ('gpgv.status', 'gpgv.log', 'release_key.gpg')},
}
(verification / 'report.json').write_text(json.dumps(verification_record, indent=2, sort_keys=True) + '\n')

export = cxx / 'cxx-export/usr'
shutil.copytree(export / 'include/c++', sysroot / 'usr/include/c++')
for name in ('libstdc++.a', 'libsupc++.a'):
    shutil.copyfile(export / 'lib' / name, sysroot / 'usr/lib' / name)
archives = sysroot / 'usr/lib'
unwind = cxx / 'unwind'
libgcc = archives / 'libgcc.a'
from_c = read_archive(libgcc)
assert GLIBC_UNWINDER_MEMBERS <= from_c.keys()
objects = [unwind / name for name in sorted(GLIBC_UNWINDER_MEMBERS)]
subprocess.run(['x86_64-elf-ar', 'rcsD', libgcc, *objects], check=True)
merged = read_archive(libgcc)
assert merged.keys() == from_c.keys()
assert all(merged[name] == from_c[name] for name in from_c.keys() - GLIBC_UNWINDER_MEMBERS)
assert all(merged[path.name] == path.read_bytes() for path in objects)
assert GLIBC_UNWINDER_SYMBOLS <= (strong_undefined_symbols(merged['unwind-dw2-fde.o'])
                                 | strong_undefined_symbols(merged['unwind-dw2.o']))

materials = sysroot / 'usr/share/xos-glibc/cxx'
(materials / 'port/keys').mkdir(parents=True)
(materials / 'licenses').mkdir()
shutil.copyfile(lock_path, materials / 'port/source_lock.json')
shutil.copyfile(signature, materials / 'port' / trust['signature_file'])
shutil.copyfile(key, materials / 'port' / trust['key_file'])
for name in ('COPYING3', 'COPYING.RUNTIME'):
    shutil.copyfile(cxx / 'upstream' / name, materials / 'licenses' / name)
include = 'usr/include/c++/' + lock['version']
config_name = include + '/x86_64-unknown-xos/bits/c++config.h'
config = sysroot / config_name
assert config.is_file()
macro_pattern = r'^[ \t]*#[ \t]*define[ \t]+(_GLIBCXX_[A-Z0-9_]+)[ \t]+([^\n]+)$'
previous_macros = {key: value.strip() for key, value in
                   re.findall(macro_pattern, (old / 'sysroot' / config_name).read_text(), re.MULTILINE)}
current_macros = {key: value.strip() for key, value in re.findall(macro_pattern, config.read_text(), re.MULTILINE)}
abi_macros = ('_GLIBCXX_USE_CXX11_ABI', '_GLIBCXX_USE_DUAL_ABI', '_GLIBCXX_INLINE_VERSION',
              '_GLIBCXX_HAS_GTHREADS')
assert all(current_macros[name] == previous_macros[name] for name in abi_macros)
assert current_macros['_GLIBCXX_HAS_GTHREADS'] == '1'
macro_diff = {name: {'old': previous_macros.get(name), 'current': current_macros.get(name)}
              for name in previous_macros.keys() | current_macros.keys()
              if previous_macros.get(name) != current_macros.get(name)}
assert sdk_snapshot(c_sdk / 'sysroot')[0] == c_binding['sdk_tree_sha256']
assert sha(c_sdk / 'manifest.json') == c_binding['sdk_manifest_sha256']
_, artifacts = sdk_snapshot(sysroot)
metadata = {**c_metadata, 'artifacts': artifacts,
            'cxx_source_verification': verification_record,
            'cxx_source_verification_report_sha256': sha(verification / 'report.json'),
            'cxx_runtime': {
                'status': 'built', 'gcc_version': lock['version'], 'source_sha256': lock['sha256'],
                'target': 'x86_64-unknown-xos', 'thread_model': 'posix', 'locale_model': 'generic',
                'include_directories': [include, include + '/x86_64-unknown-xos', include + '/backward'],
                'unwinder': {'thread_model': 'posix', 'frame_registry': 'pthread_mutex',
                             'replaced_members': {path.name: sha(path) for path in objects}},
            },
            'cxx_runtime_closure': {
                'c_sdk_manifest_sha256': c_binding['sdk_manifest_sha256'],
                'c_sdk_tree_sha256': c_binding['sdk_tree_sha256'],
                'pthread_header_sha256': sha(c_header),
                'cxx_recipe_sha256': sha(cxx / 'material/build-glibc-cxx.sh'),
                'cxx_reconfigure_recipe_sha256': sha(cxx / 'material/reconfigure_cxx.sh'),
                'configure_driver_sha256': sha(cxx / 'tools/driver'),
                'configure_terminal_archive_sha256': sha(c_sdk / 'sysroot/usr/lib/libxos_terminal.a'),
                'configure_link_probe_sha256': sha(cxx / 'std/xos_link_test'),
                'public_cxx_abi_macros': {name: current_macros[name] for name in abi_macros},
                'public_cxx_config_macro_differences': macro_diff,
                'unwinder_recipe_sha256': sha(cxx / 'material/build_unwinder.sh'),
                'configure_sha256': sha(cxx / 'std/config.h'),
                'unwinder_configure_sha256': sha(unwind / 'auto-target.h'),
                'unmodified_base_libgcc_members': len(from_c) - len(objects),
                'unwinder_dependency_receipts': {path.name: sha(path.with_suffix('.d')) for path in objects},
            }}
(output / 'manifest.json').write_text(json.dumps(metadata, indent=2, sort_keys=True) + '\n')
result = inspect_sdk('glibc', output, cxx=True, features=('directories', 'stdio_transfer', 'threads'))
print(json.dumps(result['binding'], sort_keys=True))
