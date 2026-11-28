#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the frozen GNU runtime and the installed caller's actual native inputs."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess

from archive_member_map import read_archive
from dynamic_artifacts import digest
from xypm_format import canonical, require
from xypm_sdk_profile import relative_file

repository_root = Path(__file__).resolve().parents[1]
header_roots = ('src/shared/include/', 'src/user/include/')
allowed_unused_difference = 'src/user/include/xos/net_transport.hpp'


def verify(runtime, source_revision, consumer_source, consumer_sdk):
    runtime = runtime.resolve(strict=True)
    consumer_source = consumer_source.resolve(strict=True)
    consumer_sdk = consumer_sdk.resolve(strict=True)
    metadata = json.loads((runtime / 'manifest.json').read_bytes())
    require(metadata['status'] == 'public_runtime_built_not_run' and metadata.get('public_startup'),
            'runtime is not a completed public startup candidate')
    revision = subprocess.check_output(['git', 'rev-parse', '--verify', source_revision + '^{commit}'],
                                       cwd=repository_root, text=True).strip()
    inputs = {}
    for key in ('recipe_inputs', 'port_inputs', 'native_inputs'):
        for name, expected in metadata[key].items():
            require(name not in inputs or inputs[name] == expected, 'conflicting runtime input identities')
            inputs[name] = expected
    names = sorted(inputs)
    batch = subprocess.check_output(['git', 'cat-file', '--batch'], cwd=repository_root,
                                    input=''.join(revision + ':' + name + '\n' for name in names).encode())
    offset = 0
    for name in names:
        end = batch.index(b'\n', offset)
        header = batch[offset:end].split()
        require(len(header) == 3 and header[1] == b'blob', 'frozen runtime source is missing: ' + name)
        size = int(header[2]); data = batch[end + 1:end + 1 + size]
        require(len(data) == size and hashlib.sha256(data).hexdigest() == inputs[name],
                'runtime input differs from the explicit frozen Git source: ' + name)
        offset = end + size + 2
    require(offset == len(batch), 'unexpected frozen source batch suffix')
    differences = {}
    for key in ('recipe_inputs', 'port_inputs', 'native_inputs'):
        for name, expected in metadata[key].items():
            if key == 'native_inputs':
                require(digest(relative_file(runtime / 'native_inputs', name)) == expected,
                        'frozen native snapshot changed: ' + name)
            current = digest(relative_file(consumer_source, name))
            if current != expected:
                require(key == 'native_inputs' and name == allowed_unused_difference,
                        'runtime recipe, GNU port or another native input changed: ' + name)
                differences[name] = {'frozen': expected, 'consumer': current}
    for name, expected in metadata['artifacts'].items():
        require(digest(relative_file(runtime, name)) == expected, 'frozen runtime artifact changed: ' + name)

    abi_inputs = metadata['native_abi_inputs']
    require(abi_inputs['domain'] == 'xos-glibc-dynamic-capsule-v2', 'unsupported startup ABI domain')
    require(abi_inputs['sdk_manifest_sha256'] == metadata['sdk_binding']['sdk_manifest_sha256'],
            'startup ABI and runtime C SDK identities differ')
    for name, expected in abi_inputs['startup_headers'].items():
        require(digest(relative_file(consumer_source, name)) == expected
                and digest(relative_file(consumer_sdk, 'include/xos/' + Path(name).name)) == expected,
                'public GNU startup ABI changed: ' + name)
    require(hashlib.sha256(json.dumps(abi_inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            == metadata['native_abi'], 'runtime native ABI digest differs')

    archive = read_archive(runtime / 'native_pic/libxos_terminal_pic.a')
    compiled = {}
    used_inputs = {}
    for step in metadata['steps']:
        if not step['name'].startswith('native-compile-'):
            continue
        command = step['command']
        require(step['exit_code'] == 0 and '-MMD' in command and '-MF' in command and '-o' in command,
                'native compilation did not produce actual dependencies')
        original_object = PurePosixPath(command[command.index('-o') + 1])
        original_root = original_object.parent.parent
        object_path = runtime / 'native_pic' / original_object.name
        dependency_path = runtime / 'native_pic' / (original_object.name + '.d')
        require(command[command.index('-MF') + 1] == str(original_object) + '.d', 'dependency output mismatch')
        require(object_path.name in archive and object_path.read_bytes() == archive[object_path.name],
                'native object differs from the authenticated linked archive')
        words = shlex.split(dependency_path.read_text().replace('\\\n', ' '))
        require(words and words[0] == str(original_object) + ':', 'dependency target changed')
        dependencies = []
        for value in words[1:]:
            path = PurePosixPath(value)
            if path.is_relative_to(original_root / 'native_inputs'):
                name = str(path.relative_to(original_root / 'native_inputs'))
                candidates = [name]
                actual = runtime / 'native_inputs' / name
            else:
                require(path.is_relative_to(original_root / 'native_pic/include'), 'unexpected native dependency')
                relative = str(path.relative_to(original_root / 'native_pic/include'))
                candidates = [prefix + relative for prefix in header_roots if prefix + relative in metadata['native_inputs']]
                actual = runtime / 'native_pic/include' / relative
                require(digest(relative_file(consumer_sdk, 'include/' + relative)) == digest(actual),
                        'an actually compiled native header differs in the consumer SDK: ' + relative)
            require(candidates, 'native dependency lacks a frozen input identity')
            for name in candidates:
                require(name in metadata['native_inputs'] and name not in differences
                        and digest(actual) == metadata['native_inputs'][name]
                        and digest(relative_file(consumer_source, name)) == metadata['native_inputs'][name],
                        'an actually compiled native dependency changed: ' + name)
                used_inputs[name] = metadata['native_inputs'][name]
                dependencies.append(name)
        compiled[object_path.name] = {'object_sha256': digest(object_path),
            'raw_dependency_file_sha256': digest(dependency_path), 'inputs': sorted(set(dependencies))}
    require(len(compiled) == 18 and set(compiled) == set(archive), 'native archive/dependency coverage is incomplete')
    require(not set(differences) & set(used_inputs), 'an allowed header difference affected the runtime build')
    return {'status': 'verified_frozen_runtime_and_consumer_binding', 'runtime_source_revision': revision,
        'runtime_manifest_sha256': digest(runtime / 'manifest.json'), 'native_abi': metadata['native_abi'],
        'source_groups': {key: len(metadata[key]) for key in ('recipe_inputs', 'port_inputs', 'native_inputs')},
        'frozen_git_inputs': len(inputs), 'frozen_artifacts': metadata['artifacts'],
        'unused_snapshot_header_differences': differences, 'actual_native_objects': compiled,
        'actual_native_inputs': used_inputs, 'consumer_sdk_manifest_sha256': digest(consumer_sdk / 'manifest.json'),
        'system_headers': 'unchanged complete C SDK snapshot, separately verified by the consumer builder',
        'runtime_rebuilt_for_consumer': False, 'verifier_sha256': digest(Path(__file__))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'consumer-source', 'consumer-sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--runtime-source-revision', required=True)
    args = parser.parse_args()
    args.output.write_bytes(canonical(verify(args.runtime, args.runtime_source_revision,
                                           args.consumer_source, args.consumer_sdk)))
