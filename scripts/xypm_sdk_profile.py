# SPDX-License-Identifier: Apache-2.0
"""Bind independent xypm candidates to complete, explicitly identified SDKs."""
import hashlib
import re
import stat
import struct
from pathlib import Path, PurePosixPath

from archive_member_map import read_archive
from verify_glibc_source import check_status
from xos_app import tree_receipt
from xypm_format import MAX_MANIFEST, canonical, identifier, load_json, require, sha_file, strict_json

ROOT = Path(__file__).resolve().parents[1]
COMPILER_VERSION = '16.2.0'
COMMON_FEATURES = {'stdio', 'heap', 'file_io', 'static_tls'}
GLIBC_FEATURE_FUNCTIONS = {
    'directories': {'opendir', 'readdir', 'closedir', 'mkdir', 'getcwd'},
    'threads': {'pthread_create', 'pthread_join'},
    'spawn_delegate': {'posix_spawn', '__spawni', 'execve', 'waitpid'},
    'stdio_transfer': {'fcntl', 'dup2'},
}
GLIBC_CRT = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o', 'crtend.o', 'crtn.o')
GLIBC_STDIO_RECEIVER = 'usr/lib/xos_stdio_receiver.o'
XOS_EXEC_RECEIVER = struct.pack('<QII', 0x3349424143455858, 3, 16)
GLIBC_UNWINDER_MEMBERS = {'unwind-dw2.o', 'unwind-dw2-fde.o', 'unwind-sjlj.o',
                         'unwind-c.o', 'emutls.o'}
GLIBC_UNWINDER_SYMBOLS = {'pthread_mutex_lock', 'pthread_mutex_unlock', 'pthread_once'}


def relative_file(root, name):
    require(isinstance(name, str) and name and '\\' not in name
            and all(ord(character) >= 32 and ord(character) != 127 for character in name),
            'invalid SDK relative path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and name == path.as_posix()
            and all(part not in ('.', '..') for part in path.parts),
            'SDK path must be canonical and confined: ' + name)
    current = Path(root)
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), 'SDK symlink rejected: ' + name)
    require(current.is_file(), 'SDK file missing: ' + name)
    return current


def digest_value(value, label):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value),
            'invalid SHA-256: ' + label)
    return value


def require_digest(path, expected, label):
    require(sha_file(path) == digest_value(expected, label), 'SDK digest mismatch: ' + label)


def object_value(value, label):
    require(isinstance(value, dict), 'SDK metadata object required: ' + label)
    return value


def object_member(parent, name):
    return object_value(parent.get(name, {}), name)


def metadata_snapshot(path, expected=None):
    path = Path(path)
    with path.open('rb') as stream:
        data = stream.read(MAX_MANIFEST + 1)
    value = object_value(strict_json(data), path.name)
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None:
        require(digest == digest_value(expected, str(path.name)), 'SDK metadata digest mismatch: ' + path.name)
    return value, digest


def sdk_snapshot(root):
    require(Path(root).is_dir() and not Path(root).is_symlink(), 'SDK root must be a real directory')
    for path in Path(root).rglob('*'):
        mode = path.lstat().st_mode
        require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'SDK nonregular entry rejected')
    return tree_receipt(root)


def target_object(data, label):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01',
            'SDK object must be ELF64 little-endian: ' + label)
    kind, machine, version = struct.unpack_from('<HHI', data, 16)
    require((kind, machine, version) == (1, 62, 1), 'SDK object target mismatch: ' + label)


def elf_sections(data, label):
    offset = struct.unpack_from('<Q', data, 40)[0]
    entry_size, count = struct.unpack_from('<HH', data, 58)
    require(entry_size == 64 and count > 0 and offset + count * entry_size <= len(data),
            'invalid ELF section table: ' + label)
    return [struct.unpack_from('<IIQQQQIIQQ', data, offset + index * entry_size)
            for index in range(count)]


def require_stdio_marker(data, label):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01',
            'invalid ELF for glibc stdio receiver: ' + label)
    sections = elf_sections(data, label)
    names_index = struct.unpack_from('<H', data, 62)[0]
    require(names_index < len(sections), 'invalid ELF section names: ' + label)
    names_section = sections[names_index]
    start, size = names_section[4:6]
    require(names_section[1] == 3 and start + size <= len(data),
            'invalid ELF section names: ' + label)
    names = data[start:start + size]
    markers = [section for section in sections
               if names[section[0]:section[0] + 10] == b'.xos.exec\0']
    require(len(markers) == 1, 'expected one glibc stdio receiver marker: ' + label)
    _, kind, flags, _, start, size, *_ = markers[0]
    require(kind == 1 and flags & 7 == 2 and size == len(XOS_EXEC_RECEIVER)
            and data[start:start + size] == XOS_EXEC_RECEIVER,
            'invalid glibc stdio receiver marker: ' + label)


def strong_undefined_symbols(data, label='glibc unwinder'):
    """Read strong undefined symbols from the bounded ELF64 symbol table."""
    target_object(data, label)
    sections = elf_sections(data, label)
    symbols = set()
    for section in sections:
        if section[1] != 2:  # SHT_SYMTAB
            continue
        begin, size, link, stride = section[4], section[5], section[6], section[9]
        require(stride == 24 and size % stride == 0 and begin + size <= len(data)
                and link < len(sections) and sections[link][1] == 3, 'invalid ELF symbol table: ' + label)
        strings = sections[link]
        require(strings[4] + strings[5] <= len(data), 'invalid ELF string table: ' + label)
        names = data[strings[4]:strings[4] + strings[5]]
        for position in range(begin, begin + size, stride):
            name, info, _, index, _, _ = struct.unpack_from('<IBBHQQ', data, position)
            if index != 0 or info >> 4 != 1:  # Undefined STB_GLOBAL only.
                continue
            require(name < len(names) and names.find(b'\0', name) >= 0,
                    'invalid ELF symbol name: ' + label)
            raw = names[name:names.index(b'\0', name)]
            symbols.add(raw.decode('ascii'))
    return symbols


def link_inputs(root, archives, objects, archive_member_hashes=None):
    members = {}
    for name in archives:
        archive = read_archive(relative_file(root, name))
        require(archive, 'SDK archive is empty: ' + name)
        for member, data in archive.items():
            target_object(data, name + ':' + member)
        for member, expected in (archive_member_hashes or {}).get(name, {}).items():
            require(member in archive and hashlib.sha256(archive[member]).hexdigest() == expected,
                    'SDK archive member digest mismatch: ' + name + ':' + member)
        if name == 'usr/lib/libgcc.a' and name in (archive_member_hashes or {}):
            symbols = set()
            for member in ('unwind-dw2-fde.o', 'unwind-dw2.o'):
                symbols.update(strong_undefined_symbols(archive[member]))
            require(GLIBC_UNWINDER_SYMBOLS <= symbols,
                    'glibc C++ unwinder lacks strong pthread dependencies')
        members[name] = len(archive)
    for name in objects:
        target_object(relative_file(root, name).read_bytes(), name)
    script = relative_file(root, 'user.ld').read_text()
    require('OUTPUT_FORMAT(elf64-x86-64)' in script and 'ENTRY(_start)' in script,
            'SDK linker layout target mismatch')
    return members


def source_binding(build, sdk, metadata, *, cxx=False):
    prefix = 'cxx_' if cxx else ''
    key = prefix + 'source_verification'
    record = metadata.get(key)
    require(isinstance(record, dict) and record.get('status') == 'upstream_signature_verified'
            and type(record.get('gpgv_exit')) is int and record['gpgv_exit'] == 0,
            'SDK source authentication missing: ' + key)
    directory = 'gcc_source_verification' if cxx else 'source_verification'
    report = relative_file(build, directory + '/report.json')
    report_digest = digest_value(metadata.get(key + '_report_sha256'), key + ' report')
    reported, _ = metadata_snapshot(report, report_digest)
    require(canonical(reported) == canonical(record), 'SDK source authentication report differs: ' + key)
    evidence = record.get('evidence')
    require(isinstance(evidence, dict) and {'gpgv.status', 'gpgv.log', 'release_key.gpg'} <= evidence.keys(),
            'SDK source authentication evidence incomplete: ' + key)
    for name, expected in evidence.items():
        require_digest(relative_file(build / directory, name), expected, key + '/' + name)
    verification_files = {directory + '/report.json': report_digest}
    verification_files.update({directory + '/' + name: digest for name, digest in evidence.items()})
    materials = 'usr/share/xos-glibc/cxx/port' if cxx else 'usr/share/xos-glibc/port'
    lock_path = relative_file(sdk, materials + '/source_lock.json')
    lock, lock_digest = metadata_snapshot(lock_path, digest_value(record.get('lock_sha256'), key + ' source lock'))
    archive_digest = lock.get('sha256') if cxx else lock.get('archive_sha256')
    require(digest_value(archive_digest, 'source archive') == record.get('archive_sha256'),
            'SDK source archive/authentication mismatch')
    trust = lock.get('signer_trust', {})
    require(isinstance(trust, dict) and record.get('trust_record') == trust,
            'SDK source signer trust record mismatch')
    signature = object_member(record, 'signature')
    for name in ('primary_fingerprint', 'signing_fingerprint'):
        fingerprint = trust.get(name)
        require(isinstance(fingerprint, str) and re.fullmatch(r'(?:[0-9A-F]{40}|[0-9A-F]{64})', fingerprint)
                and signature.get(name) == fingerprint, 'SDK source signer mismatch: ' + name)
    status_bytes = relative_file(build / directory, 'gpgv.status').read_bytes()
    require(hashlib.sha256(status_bytes).hexdigest() == evidence['gpgv.status'],
            'SDK source status changed during validation')
    observed = check_status(record['gpgv_exit'], status_bytes.decode('utf-8'), trust)
    require(canonical(observed) == canonical(signature), 'SDK source signature status record mismatch')
    key_name = trust.get('key_file', '')
    signature_name = trust.get('signature_file', '')
    require_digest(relative_file(sdk / materials, key_name), record.get('key_sha256'), key + ' key')
    require(record.get('key_sha256') == trust.get('key_sha256'), 'SDK signer key lock mismatch')
    require_digest(relative_file(sdk / materials, signature_name), record.get('signature_sha256'), key + ' signature')
    require(record.get('signature_sha256') == lock.get('signature_sha256'), 'SDK signature lock mismatch')
    return {'status': 'upstream_signature_verified', 'report_sha256': report_digest,
            'source_lock_sha256': lock_digest, 'archive_sha256': archive_digest,
            'key_sha256': record['key_sha256'], 'signature_sha256': record['signature_sha256'],
            'primary_fingerprint': trust['primary_fingerprint'],
            'signing_fingerprint': trust['signing_fingerprint'],
            'verification_files': verification_files}, lock


def newlib_binding(sdk, metadata, files, cxx, features):
    require(type(metadata.get('abi')) is int and metadata['abi'] == 1 and metadata.get('target') == 'x86_64-elf'
            and metadata.get('runtime_model') == 'single', 'newlib SDK ABI/target/runtime mismatch')
    require(isinstance(metadata.get('build_id'), str)
            and re.fullmatch(r'[0-9a-f]{16}', metadata['build_id']),
            'newlib SDK build_id must be a 16-digit lowercase hexadecimal identity')
    libc = object_member(metadata, 'libc')
    require(libc.get('name') == 'newlib', 'SDK runtime family mismatch: expected newlib')
    version = libc.get('version')
    require(isinstance(version, str) and re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', version),
            'invalid newlib version')
    header = relative_file(sdk, 'include/_newlib_version.h').read_text()
    match = re.search(r'^#define\s+_NEWLIB_VERSION\s+"([^"]+)"', header, re.M)
    require(match and (version == match[1] or version.startswith(match[1] + '.')),
            'newlib header/manifest version mismatch')
    require('usr/include/features.h' not in files, 'glibc header layout in newlib SDK')
    for name in ('libc', 'libm'):
        require_digest(relative_file(sdk, 'lib/' + name + '.a'), libc.get(name + '_sha256'), name)
    provenance = object_member(metadata, 'archive_provenance')
    for group in ('manifests', 'legacy_archives'):
        entries = provenance.get(group, {})
        require(isinstance(entries, dict), 'invalid newlib archive provenance')
        for name, digest in entries.items():
            require_digest(relative_file(sdk, name), digest, name)
    archives = ['lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a', 'cpp/lib/libgcc.a']
    allowed = COMMON_FEATURES | {'directories', 'stdio_transfer', 'spawn_delegate'}
    require(features <= allowed, 'unsupported newlib candidate feature')
    versions = object_member(metadata, 'process_extensions').get('startup_versions', [])
    require(isinstance(versions, list) and all(type(version) is int for version in versions)
            and 3 in versions, 'newlib candidate requires startup v3 SDK')
    cxx_binding = None
    if cxx:
        archives += ['cpp/lib/libstdc++.a', 'cpp/lib/libsupc++.a']
        include = 'cpp/include/c++/' + COMPILER_VERSION
        relative_file(sdk, include + '/vector')
        relative_file(sdk, include + '/x86_64-unknown-elf/bits/c++config.h')
        provenance_files = [name for name in ('xypm_sdk_lineage.json', 'target_runtime_provenance.json') if name in files]
        require(provenance_files, 'newlib C++ runtime provenance missing')
        if 'xypm_sdk_lineage.json' in provenance_files:
            lineage, _ = metadata_snapshot(sdk / 'xypm_sdk_lineage.json', files['xypm_sdk_lineage.json'])
            require(lineage.get('libc') == libc, 'newlib C++ lineage libc mismatch')
            cpp_archives = object_member(lineage, 'cpp_archives')
            for name in ('libstdc++.a', 'libsupc++.a', 'libgcc.a'):
                require_digest(relative_file(sdk, 'cpp/lib/' + name),
                               cpp_archives.get(name), 'C++ lineage ' + name)
        cxx_binding = {'gcc_version': COMPILER_VERSION, 'target': 'x86_64-unknown-elf',
                       'thread_model': 'single', 'provenance': {name: files[name] for name in provenance_files}}
    members = link_inputs(sdk, archives, ['crt0_posix.o'])
    for name in ('LICENSE', 'NOTICE', 'COPYING.NEWLIB'):
        relative_file(sdk, name)
    return {'libc_version': version, 'runtime_model': 'single',
            'compiler': {'target': 'x86_64-elf', 'version': COMPILER_VERSION},
            'source_authentication': {'status': 'legacy_snapshot'},
            'cxx_runtime': cxx_binding, 'archive_members': members,
            'link_artifacts': {name: files[name] for name in archives + ['crt0_posix.o', 'user.ld']}}


def glibc_binding(build, sdk, metadata, files, cxx, features):
    require(metadata.get('status') == 'static_sdk_built'
            and metadata.get('profile') == 'xos_glibc_static_research_v1',
            'glibc SDK must be a completed static research build')
    artifacts = metadata.get('artifacts')
    require(isinstance(artifacts, dict) and artifacts, 'glibc SDK artifacts missing')
    for name, digest in artifacts.items():
        require_digest(relative_file(sdk, name), digest, name)
    require(artifacts == files, 'glibc SDK artifact set differs from complete sysroot')
    require('include/newlib.h' not in files and 'usr/include/newlib.h' not in files,
            'newlib header layout in glibc SDK')
    source, lock = source_binding(build, sdk, metadata)
    require(metadata.get('source_sha256') == source['archive_sha256'], 'glibc source identity mismatch')
    version = lock.get('version')
    require(isinstance(version, str) and re.fullmatch(r'\d+\.\d+', version), 'invalid glibc version')
    header = relative_file(sdk, 'usr/include/features.h').read_text()
    for macro, value in zip(('__GLIBC__', '__GLIBC_MINOR__'), version.split('.')):
        match = re.search(r'^#\s*define\s+' + macro + r'\s+(\d+)\b', header, re.M)
        require(match and match[1] == value, 'glibc header/source version mismatch')
    stubs = metadata.get('stub_functions')
    require(isinstance(stubs, list) and all(isinstance(name, str) for name in stubs),
            'glibc SDK stub function record missing')
    require(not {'pthread_create', 'pthread_join', 'open', 'read', 'write', 'close'} & set(stubs),
            'glibc SDK lacks required G2/G3 runtime operations')
    allowed = COMMON_FEATURES | GLIBC_FEATURE_FUNCTIONS.keys()
    require(features <= allowed, 'unsupported glibc candidate feature')
    for feature in features:
        require(not GLIBC_FEATURE_FUNCTIONS.get(feature, set()) & set(stubs),
                'glibc SDK feature still has stubs: ' + feature)
    if 'spawn_delegate' in features:
        relative_file(sdk, 'usr/lib/libxos_process.a')
        relative_file(sdk, 'usr/include/xos/spawn.hpp')
    tools = object_member(metadata, 'tools')
    tool = object_member(tools, 'x86_64-elf-gcc')
    require(tool.get('available') is True and type(tool.get('version_exit_code')) is int
            and tool['version_exit_code'] == 0 and isinstance(tool.get('version'), str)
            and re.search(r'\b' + re.escape(COMPILER_VERSION) + r'\b', tool['version']),
            'glibc compiler identity/version mismatch')
    compiler = {'target': 'x86_64-elf', 'version': COMPILER_VERSION,
                'gcc_sha256': digest_value(tool.get('sha256'), 'glibc GCC')}
    archives = ['usr/lib/libc.a', 'usr/lib/libm.a', 'usr/lib/libgcc.a']
    for optional in ('usr/lib/libgcc_eh.a', 'usr/lib/libxos_process.a', 'usr/lib/libxos_terminal.a'):
        if optional in files:
            archives.append(optional)
    relative_file(sdk, 'usr/lib/compiler-include/stddef.h')
    cxx_binding = None
    member_hashes = {}
    if cxx:
        require('usr/lib/libgcc_eh.a' not in files,
                'glibc C++ separate unwind archive needs a matching profile')
        runtime = object_member(metadata, 'cxx_runtime')
        require(runtime.get('status') == 'built' and runtime.get('gcc_version') == COMPILER_VERSION
                and runtime.get('target') == 'x86_64-unknown-xos'
                and runtime.get('thread_model') == 'posix' and runtime.get('locale_model') == 'generic',
                'glibc C++ runtime identity/model mismatch')
        include = 'usr/include/c++/' + COMPILER_VERSION
        expected = [include, include + '/x86_64-unknown-xos', include + '/backward']
        require(runtime.get('include_directories') == expected, 'glibc C++ include layout mismatch')
        relative_file(sdk, include + '/vector')
        relative_file(sdk, include + '/x86_64-unknown-xos/bits/c++config.h')
        cxx_source, gcc_lock = source_binding(build, sdk, metadata, cxx=True)
        require(gcc_lock.get('version') == COMPILER_VERSION
                and runtime.get('source_sha256') == cxx_source['archive_sha256'],
                'glibc C++ source identity mismatch')
        cxx_tool = object_member(tools, 'x86_64-elf-g++')
        require(cxx_tool.get('available') is True and type(cxx_tool.get('version_exit_code')) is int
                and cxx_tool['version_exit_code'] == 0 and isinstance(cxx_tool.get('version'), str)
                and re.search(r'\b' + re.escape(COMPILER_VERSION) + r'\b', cxx_tool['version']),
                'glibc C++ compiler identity missing')
        compiler['gxx_sha256'] = digest_value(cxx_tool.get('sha256'), 'glibc G++')
        unwinder = object_member(runtime, 'unwinder')
        require(unwinder.get('thread_model') == 'posix'
                and unwinder.get('frame_registry') == 'pthread_mutex',
                'glibc C++ unwinder thread model mismatch')
        replaced = object_member(unwinder, 'replaced_members')
        require(replaced.keys() == GLIBC_UNWINDER_MEMBERS, 'glibc C++ unwinder member set mismatch')
        member_hashes['usr/lib/libgcc.a'] = {name: digest_value(digest, name)
                                            for name, digest in replaced.items()}
        archives += ['usr/lib/libstdc++.a', 'usr/lib/libsupc++.a']
        cxx_binding = {'gcc_version': COMPILER_VERSION, 'target': runtime['target'],
                       'thread_model': 'posix', 'locale_model': 'generic',
                       'include_directories': expected, 'source_authentication': cxx_source,
                       'unwinder': {'thread_model': 'posix', 'frame_registry': 'pthread_mutex',
                                    'replaced_members': member_hashes['usr/lib/libgcc.a']}}
        for name in ('COPYING3', 'COPYING.RUNTIME'):
            relative_file(sdk, 'usr/share/xos-glibc/cxx/licenses/' + name)
    objects = ['usr/lib/' + name for name in GLIBC_CRT]
    if 'stdio_transfer' in features:
        receiver = relative_file(sdk, GLIBC_STDIO_RECEIVER).read_bytes()
        require_stdio_marker(receiver, GLIBC_STDIO_RECEIVER)
        require('__xos_file_startup_capabilities' in
                strong_undefined_symbols(receiver, GLIBC_STDIO_RECEIVER),
                'glibc stdio receiver lacks the native file startup reference')
        require('KEEP(*(.xos.exec))' in relative_file(sdk, 'user.ld').read_text(),
                'glibc linker script does not retain the stdio receiver marker')
        objects.append(GLIBC_STDIO_RECEIVER)
    members = link_inputs(sdk, archives, objects, member_hashes)
    for name in ('COPYING.LIB', 'LICENSES'):
        relative_file(sdk, 'usr/share/xos-glibc/' + name)
    return {'libc_version': version, 'runtime_model': 'threaded', 'compiler': compiler,
            'source_authentication': source, 'cxx_runtime': cxx_binding,
            'archive_members': members,
            'link_artifacts': {name: files[name] for name in archives + objects + ['user.ld']}}


def inspect_sdk(runtime_family, location, *, cxx=False, features=()):
    require(runtime_family in ('newlib', 'glibc'), 'unknown runtime family')
    require(not Path(location).is_symlink(), 'SDK root symlink rejected')
    location = Path(location).resolve(strict=True)
    require(location.is_dir(), 'SDK location must be a directory')
    sdk = location / 'sysroot' if runtime_family == 'glibc' else location
    manifest = relative_file(location, 'manifest.json')
    metadata, before = metadata_snapshot(manifest)
    declared = metadata.get('runtime_family')
    if declared is not None:
        require(declared == runtime_family, 'SDK declared runtime family mismatch')
    if runtime_family == 'newlib':
        require(object_member(metadata, 'libc').get('name') == 'newlib', 'SDK runtime family mismatch')
    else:
        require(metadata.get('profile') == 'xos_glibc_static_research_v1', 'SDK runtime family mismatch')
    digest, files = sdk_snapshot(sdk)
    selected = COMMON_FEATURES | set(features)
    binding = (newlib_binding(sdk, metadata, files, cxx, selected) if runtime_family == 'newlib'
               else glibc_binding(location, sdk, metadata, files, cxx, selected))
    require(sha_file(manifest) == before and sdk_snapshot(sdk)[0] == digest,
            'SDK inputs changed during profile validation')
    sources = [binding['source_authentication']]
    if binding['cxx_runtime']:
        sources.append(binding['cxx_runtime'].get('source_authentication', {}))
    for source in sources:
        for name, expected in source.get('verification_files', {}).items():
            require_digest(relative_file(location, name), expected, 'source evidence after validation: ' + name)
    binding.update(format_version=1, runtime_family=runtime_family,
                   sdk_manifest_sha256=before, sdk_tree_sha256=digest)
    return {'location': location, 'binding': binding,
            'features': sorted(selected | ({'cxx_runtime'} if cxx else set()))}


def profile_identity(runtime_family, profile_id):
    identifier(profile_id)
    require(profile_id.startswith('xos-x86_64-' + runtime_family + '-'),
            'candidate id must include its xos-x86_64 runtime family prefix')


def profile_fields(runtime_family, profile_id, inspected):
    binding = inspected['binding']
    profile = {'format_version': 1, 'id': profile_id, 'architecture': 'x86_64',
               'byte_order': 'little', 'word_bits': 64, 'syscall_abi': 1, 'startup_version': 3,
               'compiler_version': COMPILER_VERSION, 'runtime_family': runtime_family,
               'runtime_model': binding['runtime_model'],
               'layout': 'glibc_static_native_tls_v1' if runtime_family == 'glibc'
                         else 'e08_static_tls_main_stack_128k_c3_stdio',
               'features': inspected['features'], 'sdk_tree_sha256': [binding['sdk_tree_sha256']],
               'sdk_binding': binding, 'verified_system_builds': [],
               'status': 'candidate_guest_not_run'}
    return profile


def candidate_profile(runtime_family, location, profile_id, *, cxx=False, features=()):
    profile_identity(runtime_family, profile_id)
    for path in (ROOT / 'config/package').glob('*.json'):
        if not path.name.endswith('.schema.json'):
            require(load_json(path).get('id') != profile_id, 'frozen profile id cannot be reused')
    inspected = inspect_sdk(runtime_family, location, cxx=cxx, features=features)
    return profile_fields(runtime_family, profile_id, inspected)


def verify_profile(profile, runtime_family, location):
    require(isinstance(profile, dict) and profile.get('runtime_family') == runtime_family,
            'profile runtime family mismatch')
    features = profile.get('features')
    require(isinstance(features, list) and all(isinstance(name, str) for name in features),
            'invalid profile features')
    require(features == sorted(set(features)), 'profile features must be unique and sorted')
    profile_identity(runtime_family, profile.get('id'))
    inspected = inspect_sdk(runtime_family, location, cxx='cxx_runtime' in features,
                            features=set(features) - {'cxx_runtime'})
    wanted = profile_fields(runtime_family, profile['id'], inspected)
    require(canonical(profile) == canonical(wanted), 'profile differs from the complete SDK binding')
    return {'status': 'candidate_binding_verified', 'runtime_family': runtime_family,
            'profile_id': profile['id'], 'profile_sha256': hashlib.sha256(canonical(profile)).hexdigest(),
            'sdk_tree_sha256': wanted['sdk_binding']['sdk_tree_sha256'],
            'guest_qualification': 'not_run'}
