#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture successful compiler invocations and bind actual ar members to them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from archive_member_map import read_archive, verify_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('compile', 'archive'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--declaration-class', required=True)
    separator = sys.argv.index('--') if '--' in sys.argv else len(sys.argv)
    args = parser.parse_args(sys.argv[1:separator])
    arguments = sys.argv[separator + 1:]
    if not arguments:
        parser.error('a compiler command or archive path is required after --')
    capture = capture_build(args.root, args.build_id, args.declaration_class)
    if args.action == 'compile':
        return capture.compile(arguments)
    for archive in arguments:
        print(capture.archive(Path(archive)))
    return 0


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + '.' + str(os.getpid()) + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


class capture_build:
    def __init__(self, root, build_id, declaration_class):
        if not build_id or not declaration_class:
            raise ValueError('build id and declaration class are required')
        self.root = Path(root).resolve()
        self.build_id = build_id
        self.declaration_class = declaration_class
        self.directory = self.root / 'provenance' / digest(build_id.encode())[:20]
        self.records = self.directory / 'objects'
        self.sources = self.directory / 'sources'
        self.records.mkdir(parents=True, exist_ok=True)
        self.sources.mkdir(exist_ok=True)
        self.generator = self.directory / 'archive_provenance.py'
        if not self.generator.exists():
            shutil.copyfile(__file__, self.generator)
        elif self.generator.read_bytes() != Path(__file__).read_bytes():
            raise ValueError('capture generator changed: choose a new build id')

    def launcher(self):
        return [sys.executable, str(Path(__file__).resolve()), 'compile',
                '--root', str(self.root), '--build-id', self.build_id,
                '--declaration-class', self.declaration_class, '--']

    def compile(self, command):
        inputs = compilation_inputs(command[1:])
        source_bytes = inputs[0].read_bytes() if inputs else None
        result = subprocess.run(command)
        if result.returncode or inputs is None:
            return result.returncode
        source, target = inputs
        if target.resolve() == Path(os.devnull).resolve():
            return 0
        if source.read_bytes() != source_bytes:
            raise ValueError(f'source changed while compiling: {source}')
        self.record(source, target, command, source_bytes)
        return 0

    def record(self, source, target, command, source_bytes=None):
        source, target = Path(source).resolve(), Path(target).resolve()
        content = source.read_bytes() if source_bytes is None else source_bytes
        source_hash = digest(content)
        snapshot = self.sources / (source_hash + source.suffix)
        if not snapshot.exists():
            snapshot.write_bytes(content)
        key = digest(str(target).encode())
        write_json(self.records / (key + '.json'), {
            'build_id': self.build_id, 'object': str(target.relative_to(self.root)),
            'object_sha256': digest(target.read_bytes()),
            'source': snapshot.relative_to(self.root).as_posix(),
            'source_sha256': source_hash, 'source_name': source.name,
            'command_sha256': digest(json.dumps(list(map(str, command))).encode()),
            'declaration_class': self.declaration_class,
        })

    def archive(self, archive):
        archive = Path(archive).resolve()
        if not archive.is_relative_to(self.root):
            snapshot = self.directory / 'archives' / digest(archive.read_bytes()) / archive.name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(archive, snapshot)
            archive = snapshot
        records = [json.loads(path.read_text()) for path in sorted(self.records.glob('*.json'))]
        by_hash = {}
        for record in records:
            if record['build_id'] != self.build_id:
                raise ValueError('foreign compiler record in capture directory')
            by_hash.setdefault(record['object_sha256'], []).append(record)
        members = []
        for name, payload in read_archive(archive).items():
            matches = by_hash.get(digest(payload), [])
            named = [record for record in matches if Path(record['object']).name == name]
            matches = named or matches
            identities = {(record['source'], record['declaration_class']) for record in matches}
            if len(identities) != 1:
                raise ValueError(f'{archive.name}:{name}: no unique captured compilation ({len(identities)})')
            record = matches[0]
            members.append({key: record[key] for key in
                            ('source', 'source_sha256', 'source_name', 'declaration_class',
                             'object_sha256', 'command_sha256')} | {'member': name, 'derived': False})
        path = archive.with_name(archive.name + '.member_manifest.json')
        write_json(path, {'version': 1, 'archive': archive.relative_to(self.root).as_posix(),
                         'archive_sha256': digest(archive.read_bytes()), 'build_id': self.build_id,
                         'generator': self.generator.relative_to(self.root).as_posix(),
                         'generator_sha256': digest(self.generator.read_bytes()),
                         'capture': 'compiler-invocation-and-object-bytes', 'members': members})
        verify_manifest(path, self.root, self.build_id)
        return path

    def archives(self, directory):
        result = {}
        for archive in sorted(Path(directory).rglob('*.a')):
            manifest = self.archive(archive)
            result[manifest.relative_to(self.root).as_posix()] = digest(manifest.read_bytes())
        return result


def copy_archive_provenance(manifest, source_root, destination, root):
    """Copy a previously built dependency without relabeling its compilation id."""
    manifest, source_root = Path(manifest), Path(source_root)
    destination, root = Path(destination).resolve(), Path(root).resolve()
    content = json.loads(manifest.read_text())
    verify_manifest(manifest, source_root, content['build_id'])
    if digest(destination.read_bytes()) != content['archive_sha256']:
        raise ValueError('imported archive differs from the captured artifact')
    directory = root / 'provenance' / 'imports' / digest(manifest.read_bytes())[:20]
    directory.mkdir(parents=True, exist_ok=True)
    origin = directory / 'origin_manifest.json'
    origin.write_bytes(manifest.read_bytes())
    for record in [*content['members'], {'source': content['generator'], 'source_sha256': content.get('generator_sha256')}]:
        source = source_root / record['source']
        target = directory / (digest(source.read_bytes()) + source.suffix)
        shutil.copyfile(source, target)
        record['source'] = target.relative_to(root).as_posix()
        if 'member' not in record:
            content['generator'] = record['source']
    content['archive'] = destination.relative_to(root).as_posix()
    content['imported_manifest_sha256'] = digest(manifest.read_bytes())
    content['imported_manifest'] = origin.relative_to(root).as_posix()
    output = destination.with_name(destination.name + '.member_manifest.json')
    write_json(output, content)
    verify_manifest(output, root, content['build_id'])
    return output


def compilation_inputs(arguments):
    expanded = []
    for argument in arguments:
        expanded.extend(shlex.split(Path(argument[1:]).read_text()) if argument.startswith('@') else [argument])
    if '-c' not in expanded:
        return None
    sources, target, index = [], None, 0
    operand_options = {'-o', '-I', '-isystem', '-iquote', '-idirafter', '-include', '-imacros',
                       '-MF', '-MT', '-MQ', '-x', '-isysroot', '--sysroot', '-B'}
    while index < len(expanded):
        argument = expanded[index]
        if argument in operand_options:
            if index + 1 == len(expanded):
                raise ValueError(f'missing compiler operand: {argument}')
            if argument == '-o':
                target = Path(expanded[index + 1])
            index += 2
            continue
        if argument.startswith('-o') and len(argument) > 2:
            target = Path(argument[2:])
        elif not argument.startswith('-') and Path(argument).suffix in ('.c', '.cc', '.cpp', '.cxx', '.C', '.s', '.S'):
            sources.append(Path(argument))
        index += 1
    if len(sources) != 1:
        raise ValueError('capture requires one named source per compilation')
    return sources[0], target or Path(sources[0].stem + '.o')


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f'archive provenance: {error}')
