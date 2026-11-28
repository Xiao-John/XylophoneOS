#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package a verified native GNU generation at immutable content-addressed paths.

Produces unsigned material. A separately provisioned release key signs it with
xypm_release.py; an authenticated guest publisher must still approve the root.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from dynamic_artifacts import INTERPRETER, generation_record
from xypm_format import canonical, identifier, load_json, pack_package, require, sha_file
from xypm_repository import create_repository, make_lock, write_metadata


def build(program, profile, package_id, licenses, output):
    identifier(package_id)
    program = Path(program).resolve(strict=True)
    record = load_json(program / 'manifest.json')
    require(record['status'] == 'built_not_run' and record['public_startup'],
            'a complete native GNU generation build is required')
    require(record['sdk_binding']['sdk_manifest_sha256'] == profile['sdk_binding']['sdk_manifest_sha256'],
            'program generation belongs to a different SDK manifest')
    original_generation = program / record['generation']['local']
    require(sha_file(original_generation) == record['generation']['sha256'], 'program manifest changed')
    entries, payload = [], {}
    encoded = original_generation.read_bytes()
    count = struct.unpack_from('<I', encoded, 24)[0]
    require(4 <= count <= 12 and len(encoded) == 128 + count * 512, 'invalid original generation count')
    for index in range(count):
        original_path = encoded[128 + index * 512 + 328:128 + index * 512 + 456].split(b'\0', 1)[0].decode('ascii')
        source = program / record['files'][original_path]['local']
        digest = sha_file(source)
        require(digest == record['files'][original_path]['sha256'], 'program object changed')
        destination = INTERPRETER if original_path == INTERPRETER else '/usr/lib/xos/objects/' + digest + '.elf'
        require(destination not in payload, 'duplicate generation payload path')
        payload[destination] = source
        entries.append((source, destination))
    # The production generation encoder rechecks roles, identity, complete ELF
    # dependencies, mappings and symbol versions after rewriting the paths.
    body, _ = generation_record(record['generation']['id'],
        profile['sdk_binding']['sdk_manifest_sha256'], record['native_abi'], entries)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    stage = output / 'stage'
    stage.mkdir()
    files = []

    def add(relative, data, role='data'):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files.append({'path': relative, 'type': 'file', 'size': len(data),
                      'sha256': hashlib.sha256(data).hexdigest(), 'role': role})

    for index, (_, destination) in enumerate(entries):
        add(destination[1:], payload[destination].read_bytes(), 'executable' if index == 0 else 'data')
    license_paths = []
    for ordinal, path in enumerate(licenses):
        relative = 'usr/share/licenses/' + package_id + '/LICENSE_' + str(ordinal)
        add(relative, Path(path).read_bytes())
        license_paths.append(relative)
    require(license_paths, 'publisher must provide application/runtime license notices')
    receipt_path = 'usr/share/' + package_id + '/generation_build.json'
    receipt = canonical({'builder': 'build_xypm_distribution.py', 'program_manifest_sha256': sha_file(program / 'manifest.json'),
                         'program_sdk_binding': record['sdk_binding'], 'native_sdk_binding': record['native_sdk_binding'],
                         'generation_sha256': hashlib.sha256(body).hexdigest(), 'generation_id': record['generation']['id'],
                         'input_objects': record['files'], 'output_objects': [path for _, path in entries]})
    add(receipt_path, receipt)
    manifest = {'format_version': 1, 'id': package_id, 'upstream_version': '1.0', 'revision': 0,
                'target_profile': profile['id'], 'required_features': [], 'runtime_dependencies': [],
                'files': files, 'licenses': license_paths,
                'build_receipt': {'path': receipt_path, 'sha256': hashlib.sha256(receipt).hexdigest()},
                'source': 'Native GNU generation built from the source-bound program build receipt'}
    package = output / 'application.xpk'
    pack_package(stage, manifest, package)
    repository = output / 'repository'
    create_repository([package], repository, profile)
    lock = make_lock(repository, [sha_file(package)], profile)
    write_metadata(output / 'lock.json', lock)
    (repository / 'generation.bin').write_bytes(body)
    result = {'status': 'unsigned_distribution_built', 'package_id': package_id,
              'package_sha256': sha_file(package), 'generation_id': record['generation']['id'],
              'generation_sha256': hashlib.sha256(body).hexdigest(),
              'profile_sha256': hashlib.sha256(canonical(profile)).hexdigest(),
              'program_manifest_sha256': sha_file(program / 'manifest.json'),
              'repository': 'repository', 'lock': 'lock.json',
              'objects': [{'path': destination, 'sha256': sha_file(source)} for source, destination in entries]}
    (output / 'report.json').write_bytes(canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('program', 'profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--package-id', required=True)
    parser.add_argument('--license', type=Path, action='append', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.program, load_json(args.profile), args.package_id, args.license, args.output), indent=2))


if __name__ == '__main__':
    main()
