#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify path-only evidence conversions against their original Git bytes.

This checks the conversion ledger, legacy indexes, current export indexes and
recorded archive members. It does not erase history or re-run guest tests.
"""
import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from verify_evidence_index import checkout_reader, git_reader, no_duplicates, safe_path, verify
from evidence_host_command_templates import host_documents, template_qemu_json, template_reviewed_host_data

conversion_dir = 'docs/evidence_exports/issue37'
host_document_notice = ('> **路径模板：** 本历史记录中的宿主临时根目录为可配置占位符；原始字节保留在源提交。\n\n').encode('utf-8')
patterns = [
    ('WORKTREE', re.compile(rb'(?i)/us' rb'ers/[^/\s"\'\\]+/Documents/ChatGPT/os/[^/\s,;"\'\\]+')),
    ('TOOLCHAIN', re.compile(rb'(?i)/us' rb'ers/[^/\s"\'\\]+/homebrew')),
    ('HOME', re.compile(rb'(?i)/us' rb'ers/[^/\s,;"\'\\]+')),
    ('PYTHON', re.compile(rb'/Library/Frame' rb'works/Python\.framework/Versions/[^/\s,;"\'\\]+')),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected_export(data, name=''):
    for kind, pattern in patterns:
        data = pattern.sub(lambda match: ('${XOS_' + kind + '_' + digest(match.group())[:12].upper() + '}').encode(), data)
    if name.endswith(('.json', '.json.gz')):
        data, _, _ = template_qemu_json(data)
    data, _ = template_reviewed_host_data(data, name)
    return data


def raw_payload(data):
    return gzip.decompress(data) if data.startswith(b'\x1f\x8b') else data


def verify_index_semantics(old_data, new_data, ledger):
    """Permit index hash updates without changing historical input metadata."""
    path = Path(ledger['original_index_path'])
    if path.suffix != '.json':
        return
    old = json.loads(expected_export(old_data, str(path)), object_pairs_hook=no_duplicates)
    new = json.loads(new_data, object_pairs_hook=no_duplicates)
    if ledger.get('bundle_path'):
        for key in old:
            if key not in ('evidence_sha256', 'bundle_sha256'):
                require(old[key] == new[key], 'legacy bundle metadata changed')
        require(old.keys() == new.keys(), 'legacy bundle metadata keys changed')
        return
    field = ledger.get('index_field')
    if field in (None, '-'):
        if isinstance(old.get('evidence_sha256'), dict):
            field = 'evidence_sha256'
        elif isinstance(old.get('files'), dict):
            field = 'files'
        else:
            field = None
    old_map = old[field] if field else old
    new_map = new[field] if field else new
    added = ledger.get('added_export_document')
    allowed = {Path(added).name} if added and Path(added).parent == path.parent else set()
    require(set(old_map) <= set(new_map) and set(new_map) - set(old_map) <= allowed,
            'legacy index keys changed unexpectedly')
    for name in old_map:
        before, after = old_map[name], new_map[name]
        require(type(before) is type(after), 'legacy index value type changed')
        if isinstance(before, dict):
            before = {k: v for k, v in before.items() if k not in ('sha256', 'bytes')}
            after = {k: v for k, v in after.items() if k not in ('sha256', 'bytes')}
            require(before == after, 'legacy index non-hash metadata changed')
    if field:
        old[field] = new[field]
        require(old == new, 'historical qualification metadata changed')


def verify_archive(old, new, info, original_index=None, export_index=None):
    changed = {item['name']: item for item in info['changed_members']}
    pax = {item['name']: item['change'] for item in info.get('pax_header_changes', [])}
    seen = set()
    unchanged = owners = 0
    with tarfile.open(fileobj=io.BytesIO(old), mode='r:gz') as before, \
            tarfile.open(fileobj=io.BytesIO(new), mode='r:gz') as after:
        old_members, new_members = before.getmembers(), after.getmembers()
        require(len(old_members) == len(new_members) == info['member_count'], 'archive member count mismatch')
        require(len(old_members) <= 20000, 'archive member limit exceeded')
        for old_member, new_member in zip(old_members, new_members):
            name = old_member.name
            path = safe_path(name)
            require(str(path) == name and name not in seen, 'unsafe or duplicate archive member')
            seen.add(name)
            require((old_member.isfile() or old_member.isdir()) and old_member.type == new_member.type,
                    'unsupported archive member type')
            for field in ('name', 'mode', 'uid', 'gid', 'mtime', 'type', 'linkname'):
                require(getattr(old_member, field) == getattr(new_member, field), 'archive metadata mismatch')
            if old_member.uname != new_member.uname or old_member.gname != new_member.gname:
                owners += 1
                require((old_member.uname == new_member.uname or new_member.uname == 'xos-redacted') and
                        (old_member.gname == new_member.gname or new_member.gname == 'xos-redacted'),
                        'unexpected archive owner change')
            difference = {key: {'original': old_member.pax_headers.get(key), 'export': new_member.pax_headers.get(key)}
                          for key in set(old_member.pax_headers) | set(new_member.pax_headers)
                          if old_member.pax_headers.get(key) != new_member.pax_headers.get(key)}
            require(difference == pax.get(name, {}), 'unrecorded archive header change')
            if not old_member.isfile():
                continue
            require(old_member.size <= 256 * 1024 * 1024 and new_member.size <= 256 * 1024 * 1024,
                    'archive member size limit exceeded')
            old_data = before.extractfile(old_member).read()
            new_data = after.extractfile(new_member).read()
            require(digest(old_data) == info['original_member_sha256'][name], 'original member hash mismatch')
            if original_index is not None:
                require(digest(old_data) == original_index[name] and digest(new_data) == export_index[name],
                        'archive index binding mismatch')
            if name in changed:
                entry = changed[name]
                require(digest(old_data) == entry['original_sha256'] and digest(new_data) == entry['export_sha256'],
                        'changed member hash mismatch')
                require(expected_export(raw_payload(old_data), name) == raw_payload(new_data), 'member has non-path changes')
            else:
                require(old_data == new_data, 'unrecorded archive member change')
                unchanged += 1
    require(set(changed) <= seen and set(pax) <= seen, 'archive change record has unknown member')
    require(unchanged == info['unchanged_member_count'] and owners == info['archive_owner_names_redacted'],
            'archive change count mismatch')
    return len(seen), len(changed)


def run(root, export_revision=None):
    root = root.resolve()
    export = git_reader(root, export_revision) if export_revision else checkout_reader(root)
    sources = {}
    try:
        manifest_path = safe_path(conversion_dir + '/manifest.json')
        manifest = json.loads(export.read(manifest_path), object_pairs_hook=no_duplicates)
        require(manifest.get('version') == 1 and isinstance(manifest.get('files'), dict), 'invalid flat manifest')
        listed = manifest['files']
        if export_revision:
            records = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', '--name-only',
                                               export.commit, '--', conversion_dir]).split(b'\0')
            actual = {Path(x.decode()).relative_to(conversion_dir).as_posix() for x in records if x}
        else:
            directory = root / conversion_dir
            actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
        actual.discard('manifest.json')
        require(set(listed) == actual, 'flat manifest coverage mismatch')
        for name, expected in listed.items():
            require(digest(export.read(safe_path(conversion_dir + '/' + name))) == expected, 'flat manifest hash mismatch')
        lineages = sorted(name for name in listed if name.endswith('_lineage.json'))
        require(lineages, 'no conversion ledgers found')
        files_checked = archives_checked = members_checked = legacy_indexes = 0
        seen_changes = set()
        for name in lineages:
            ledger = json.loads(export.read(safe_path(conversion_dir + '/' + name)), object_pairs_hook=no_duplicates)
            require(ledger.get('status') == 'DERIVED_SANITIZED_EXPORT', 'invalid conversion status')
            source_commit = ledger['source_commit']
            require(re.fullmatch(r'[0-9a-f]{40}', source_commit), 'invalid source commit')
            if source_commit not in sources:
                sources[source_commit] = git_reader(root, source_commit)
            source = sources[source_commit]
            index_path = ledger.get('original_index_path')
            old_index = new_index = None
            if index_path:
                index = safe_path(index_path)
                old_index_data, new_index_data = source.read(index), export.read(index)
                require(digest(old_index_data) == ledger['original_index_sha256'] and
                        digest(new_index_data) == ledger['export_index_sha256'], 'legacy index provenance mismatch')
                try:
                    verify_index_semantics(old_index_data, new_index_data, ledger)
                except ValueError as error:
                    raise ValueError(name + ': ' + str(error)) from error
                if ledger.get('bundle_path'):
                    old_index = json.loads(old_index_data, object_pairs_hook=no_duplicates)
                    new_index = json.loads(new_index_data, object_pairs_hook=no_duplicates)
                else:
                    field = ledger.get('index_field')
                    field = None if field in (None, '-') else field
                    suffix = ledger.get('index_suffix', '')
                    old_result = verify(root, index_path, source_commit, field, path_suffix=suffix)
                    new_result = verify(root, index_path, export_revision, field, path_suffix=suffix)
                    require(old_result['status'] == new_result['status'] == 'PASS', 'legacy source/export index mismatch')
                    legacy_indexes += 1
            added = ledger.get('added_export_document')
            if added:
                require(digest(export.read(safe_path(added))) == ledger['added_export_document_sha256'],
                        'added export notice hash mismatch')
            for change in ledger['changes']:
                path = safe_path(change['path'])
                require(str(path) not in seen_changes, 'duplicate changed path across ledgers')
                seen_changes.add(str(path))
                old, new = source.read(path), export.read(path)
                require(digest(old) == change['original_sha256'] and digest(new) == change['export_sha256'],
                        'source/export file hash mismatch')
                info = change.get('archive')
                if str(path) == ledger.get('bundle_path'):
                    info = ledger['archive']
                    require(digest(old) == old_index['bundle_sha256'] and digest(new) == new_index['bundle_sha256'],
                            'bundle hash mismatch')
                if info:
                    original_map = old_index['evidence_sha256'] if str(path) == ledger.get('bundle_path') else None
                    export_map = new_index['evidence_sha256'] if original_map is not None else None
                    members, _ = verify_archive(old, new, info, original_map, export_map)
                    archives_checked += 1
                    members_checked += members
                elif ledger.get('transformation_kind') == 'REVIEWED_HOST_DOCUMENT':
                    require(str(path) in host_documents and new == host_document_notice + expected_export(old, str(path)),
                            'reviewed host document changed beyond its notice and path templates')
                elif path.name == 'README.md':
                    require(new.endswith(expected_export(old, str(path))), 'README changed beyond path conversion and notice')
                else:
                    require(expected_export(raw_payload(old), str(path)) == raw_payload(new), 'file has non-path changes')
                files_checked += 1
        return {'status': 'PASS', 'scope': 'conversion integrity only; guest replay and historical erasure not claimed',
                'source_commits': sorted(sources), 'ledgers': len(lineages), 'changed_files': files_checked,
                'legacy_indexes': legacy_indexes, 'archives': archives_checked, 'archive_members': members_checked}
    finally:
        for source in sources.values():
            source.close()
        export.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--export-revision', help='verify the complete export at this Git commit')
    args = parser.parse_args()
    try:
        result = run(args.root, args.export_revision)
    except (OSError, EOFError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as error:
        # Errors may include a private local checkout path; reports remain safe
        # to share and the caller can inspect the failing data locally.
        print(json.dumps({'status': 'FAIL', 'error_type': type(error).__name__}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
