# SPDX-License-Identifier: Apache-2.0
"""Package a bound static glibc CPython core and its disk standard library."""

import argparse
from hashlib import sha256
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

from build_cpython_legacy import PORT, apply_patches, extract_source, hash_tree
from stage_cpython import selected_library_files
from xos_app import sdk_notices
from xypm_format import canonical, inspect_elf, load_json, pack_package, require, sha_file
from xypm_sdk_profile import metadata_snapshot, verify_profile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = 'xos.cpython'
PROGRAM = 'usr/bin/python3'
LIBRARY = 'usr/lib/python314.zip'
LANDMARK = 'usr/lib/python3.14/os.py'
RECEIPT = 'usr/share/' + PACKAGE + '/build_receipt.json'
FEATURES = {'stdio', 'heap', 'file_io', 'static_tls', 'directories', 'threads'}
BUILDERS = ('build_cpython.py', 'build_cpython_glibc.py', 'build_cpython_legacy.py')


def loaded_image(data):
    # A mapped ELF header can contain these three section-table fields,
    # which objcopy updates when it removes nonloaded debug sections.
    normalized = data[:40] + bytes(8) + data[48:60] + bytes(4) + data[64:]
    table = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    headers = data[table:table + stride * count]
    segments = []
    for offset in range(0, len(headers), stride):
        kind, _, start, _, _, length, _, _ = struct.unpack_from('<IIQQQQQQ', headers, offset)
        if kind in (1, 7):  # PT_LOAD, PT_TLS
            segments.append(sha256(memoryview(normalized)[start:start + length]).hexdigest())
    return normalized[:64], headers, segments


def stage_interpreter(binary, work, root, build, metadata):
    layout = inspect_elf(binary)
    require(layout == build['executable']['layout'] and layout['static_tls'], 'unexpected interpreter ELF layout')
    payload = binary.read_bytes()
    digest = sha256(payload).hexdigest()
    require(digest == build['executable']['sha256'] and len(payload) == build['executable']['bytes'],
            'full interpreter differs from CLI build')
    objcopy = shutil.which('x86_64-elf-objcopy')
    expected = metadata['tools']['x86_64-elf-objcopy']['sha256']
    require(objcopy is not None and sha_file(objcopy) == expected, 'objcopy differs from the SDK toolchain')
    snapshot = work / 'debug.elf'
    snapshot.write_bytes(payload)
    runtime = root / PROGRAM
    runtime.parent.mkdir(parents=True)
    subprocess.run([objcopy, '--strip-debug', str(snapshot), str(runtime)], check=True)
    runtime_bytes = runtime.read_bytes()
    require(inspect_elf(runtime) == layout and loaded_image(payload) == loaded_image(runtime_bytes),
            'debug stripping changed the loaded interpreter')
    require(sha_file(binary) == digest and sha_file(objcopy) == expected, 'interpreter or objcopy changed')
    return {'path': PROGRAM, 'sha256': sha256(runtime_bytes).hexdigest(), 'bytes': len(runtime_bytes),
            'debug_sha256': digest, 'debug_bytes': len(payload), 'strip_mode': 'strip-debug',
            'objcopy_sha256': expected, 'layout': layout}


def stage_library(archive, work, root):
    source = work / 'source'
    extract_source(archive, source)
    apply_patches(source)
    lib = source / 'Lib'
    output = root / LIBRARY
    output.parent.mkdir(parents=True)
    files = {}
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as bundle:
        for source_file, relative in selected_library_files(lib):
            name = relative.as_posix()
            data = source_file.read_bytes()
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, data)
            files[name] = sha256(data).hexdigest()
    require({'os.py', 'encodings/__init__.py', 'json/__init__.py'} <= files.keys(),
            'incomplete selected CPython library')
    landmark = (lib / 'os.py').read_bytes()
    require(sha256(landmark).hexdigest() == files['os.py'], 'CPython prefix landmark changed')
    (root / LANDMARK).parent.mkdir(parents=True)
    (root / LANDMARK).write_bytes(landmark)
    return {'path': LIBRARY, 'sha256': sha_file(output), 'storage': 'stored_zip', 'members': files,
            'landmark': LANDMARK}


def package(args):
    profile, profile_digest = metadata_snapshot(args.profile)
    binding = verify_profile(profile, 'glibc', args.sdk)
    require(FEATURES <= set(profile['features']), 'CPython package requires the native directory and thread profile')
    sdk_digest = profile['sdk_binding']['sdk_manifest_sha256']
    metadata, _ = metadata_snapshot(args.sdk / 'manifest.json', sdk_digest)
    report_path = args.cpython_build / 'py0a_report.json'
    build, build_digest = metadata_snapshot(report_path)
    require(build['status'] == 'built_not_run' and build['runtime_family'] == 'glibc'
            and build['profile_file_sha256'] == profile_digest and build['sdk_binding'] == binding
            and build['sdk_manifest_sha256'] == sdk_digest and build['static_extensions'] == [],
            'CPython build differs from the static glibc SDK/profile')
    port = hash_tree(PORT)
    builders = {name: sha_file(ROOT / 'scripts' / name) for name in BUILDERS}
    require(build['port_inputs'] == port and build['builder_inputs'] == builders,
            'CPython source patch or CLI builder inputs changed')
    lock = load_json(PORT / 'source_lock.json')
    digest = lock['sha256']
    require(build['version'] == lock['version'] == '3.14.9' and
            build['source_archive_sha256'] == digest == sha_file(args.archive), 'CPython source archive differs')

    with tempfile.TemporaryDirectory(prefix='cpython_glibc_xpk_') as folder:
        work = Path(folder)
        root = work / 'root'
        elf = stage_interpreter(args.cpython_build / 'target_build/python.exe', work, root, build, metadata)
        library = stage_library(args.archive, work, root)
        license_root = 'usr/share/licenses/' + PACKAGE + '/'
        licenses = []
        for source, name in [(work / 'source/LICENSE', 'cpython/LICENSE'), (ROOT / 'LICENSE', 'xos/LICENSE'),
                             (ROOT / 'NOTICE', 'xos/NOTICE')]:
            path = license_root + name
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, root / path)
            licenses.append(path)
        for source, name in sdk_notices(args.sdk, profile, 'c'):
            payload = source.read_bytes()
            require(sha256(payload).hexdigest() == metadata['artifacts'][name], 'SDK notice differs: ' + name)
            path = license_root + 'sdk/' + name
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(payload)
            licenses.append(path)
        receipt = {'runtime_family': 'glibc', 'sdk_manifest_sha256': sdk_digest, 'sdk_binding': binding,
                   'profile_file_sha256': profile_digest, 'source_archive_sha256': digest,
                   'cli_build_receipt_sha256': build_digest, 'packager_sha256': sha_file(__file__),
                   'interpreter': elf, 'library': library, 'unqualified': build['unqualified']}
        receipt_bytes = canonical(receipt)
        (root / RECEIPT).parent.mkdir(parents=True, exist_ok=True)
        (root / RECEIPT).write_bytes(receipt_bytes)
        files = []
        for source in sorted(root.rglob('*')):
            if source.is_file():
                path = source.relative_to(root).as_posix()
                files.append({'path': path, 'type': 'file', 'role': 'executable' if path == PROGRAM else 'data',
                              'sha256': sha_file(source), 'size': source.stat().st_size})
        manifest = {'format_version': 1, 'id': PACKAGE, 'upstream_version': build['version'], 'revision': 0,
                    'target_profile': profile['id'], 'required_features': sorted(FEATURES),
                    'runtime_dependencies': [], 'files': files, 'licenses': sorted(licenses),
                    'build_receipt': {'path': RECEIPT, 'sha256': sha256(receipt_bytes).hexdigest()},
                    'source': 'Pinned CPython source and the native static interpreter in the build receipt'}
        require(sha_file(args.archive) == digest and hash_tree(PORT) == port
                and {name: sha_file(ROOT / 'scripts' / name) for name in BUILDERS} == builders
                and sha_file(report_path) == build_digest,
                'CPython source or build changed during packaging')
        require(sha_file(args.profile) == profile_digest and verify_profile(profile, 'glibc', args.sdk) == binding,
                'glibc SDK or profile changed during packaging')
        result = pack_package(root, manifest, args.output)
    return {'status': 'candidate_packed', 'package': str(args.output), 'sha256': result['sha256'],
            'payload_files': result['payload_files'], 'interpreter': elf, 'stdlib_members': len(library['members'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpython-build', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(package(args), indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, 'CPython package: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
