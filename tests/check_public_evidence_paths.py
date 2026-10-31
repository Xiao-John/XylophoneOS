#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail closed when public evidence contains host paths or cannot be scanned.

``--index`` scans Git's actual stage-zero blobs, never the working-tree files.
``--base REF`` selects the candidate delta against REF; deletions are excluded.
Findings omit matched bytes and archive member names so reports are safe to share.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 256 * 1024 * 1024
TOTAL_LIMIT = 1024 * 1024 * 1024
MAX_DEPTH = 6
MAX_MEMBERS = 20000

# Patterns intentionally identify home directories, rather than treating every
# absolute system path as a private path. Content is scanned as bytes, including
# binary files. Single quotes are excluded as well as JSON double quotes.
PATTERNS = {
    'macos_home': rb'(?i)/us' rb'ers/[^/\\\s"\'\x00<>]+(?:/[^\s"\'\x00<>]*)?',
    'linux_home': rb'/ho' rb'me/[^/\\\s"\'\x00<>]+(?:/[^\s"\'\x00<>]*)?',
    'windows_home': rb'(?i)[a-z]:[\\/]+users[\\/]+[^\\/\s"\'\x00<>]+(?:[\\/][^\s"\'\x00<>]*)?',
    'private_temp': rb'(?i)(?:/private/tm' rb'p/|/var/fol' rb'ders/|/tm' rb'p/)[^/\s"\'\x00<>]+',
    'local_file_uri': rb'(?i)file://(?:localhost)?/(?:users|home|private/tmp|var/folders|tmp)/[^\s"\'\x00<>]+',
    'workspace_scratch': rb'/work' rb'space/scratch/[^\s"\'\x00<>]+',
    'framework_python': rb'/Library/Frame' rb'works/Python\.framework/Versions/[^\s"\'\x00<>]+',
    'codex_runtime': rb'/opt/codex/run' rb'times/[^\s"\'\x00<>]+',
}
COMPILED = {key: re.compile(value) for key, value in PATTERNS.items()}
CLASSES = {
    'macos_home': 'CONFIRMED_PRIVATE_PATH',
    'linux_home': 'CONFIRMED_PRIVATE_PATH',
    'windows_home': 'CONFIRMED_PRIVATE_PATH',
    'private_temp': 'HOST_SPECIFIC_COMMAND',
    'local_file_uri': 'NEEDS_REVIEW',
    'private_identity': 'CONFIRMED_PRIVATE_IDENTITY',
    'workspace_scratch': 'PORTABILITY_ISSUE',
    'framework_python': 'HOST_SPECIFIC_COMMAND',
    'codex_runtime': 'HOST_SPECIFIC_COMMAND',
    'absolute_command': 'PORTABILITY_ISSUE',
    'unscanned_limit': 'UNVERIFIED_ARCHIVE',
    'unreadable_archive': 'UNVERIFIED_ARCHIVE',
    'unreadable_file': 'NEEDS_REVIEW',
    'unmerged_index': 'NEEDS_REVIEW',
    'unsupported_git_object': 'NEEDS_REVIEW',
}
COMMAND_KEYS = {'qemu_command', 'commands', 'command'}
ABSOLUTE = re.compile(r'(?<![A-Za-z0-9_$}:])/(?:[A-Za-z0-9_.+@-]+/)+[A-Za-z0-9_.+@%-]*')
SYSTEM_PATHS = ('/usr/bin/', '/usr/lib/', '/usr/share/', '/usr/include/', '/bin/',
                '/sbin/', '/usr/sbin/', '/lib/', '/lib64/', '/dev/', '/proc/', '/sys/')


def finding(findings, location, category):
    findings.append({'location': location, 'category': category,
                     'classification': CLASSES[category],
                     'status': 'UNVERIFIED' if category in {
                         'unscanned_limit', 'unreadable_archive', 'unreadable_file',
                         'unmerged_index', 'unsupported_git_object'} else 'OPEN'})


def safe_location(name, identities=()):
    raw = os.fsencode(name)
    # A repository or member name can itself contain a private path.
    if any(pattern.search(raw) for pattern in COMPILED.values()) or any(i.encode().lower() in raw.lower() for i in identities):
        return 'path-sha256:' + hashlib.sha256(raw).hexdigest()[:20]
    return os.fsdecode(raw)


class Budget:
    def __init__(self, identities=()):
        self.bytes = 0
        self.members = 0
        self.identities = tuple(re.compile(rb'(?<![A-Za-z0-9_-])' + re.escape(i.encode()) +
                                           rb'(?![A-Za-z0-9_-])', re.IGNORECASE) for i in identities if i)

    def charge(self, size):
        self.bytes += size
        return self.bytes <= TOTAL_LIMIT

    def member(self):
        self.members += 1
        return self.members <= MAX_MEMBERS


def _commands(value, findings, location):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in COMMAND_KEYS:
                encoded = json.dumps(item, ensure_ascii=False)
                for match in ABSOLUTE.finditer(encoded):
                    if not match.group().startswith(SYSTEM_PATHS):
                        finding(findings, location, 'absolute_command')
                        break
            _commands(item, findings, location)
    elif isinstance(value, list):
        for item in value:
            _commands(item, findings, location)


def scan(data, location, findings, depth=0, budget=None, expected=''):
    """Scan a buffer and supported archive members without extracting to disk."""
    budget = budget or Budget()
    if depth > MAX_DEPTH or len(data) > LIMIT or not budget.charge(len(data)):
        finding(findings, location, 'unscanned_limit')
        return
    variants = [data]
    if b'\0' in data:
        # Covers UTF-16 ASCII path fragments embedded in otherwise binary data.
        variants.append(data.replace(b'\0', b''))
    for category, pattern in COMPILED.items():
        if any(pattern.search(value) for value in variants):
            finding(findings, location, category)
    if any(pattern.search(value) for pattern in budget.identities for value in variants):
        finding(findings, location, 'private_identity')
    try:
        document = json.loads(data)
        _commands(document, findings, location)
        # JSON may encode slashes, drive separators, or Unicode as escapes.
        decoded = json.dumps(document, ensure_ascii=False).replace('\\\\', '\\').encode('utf-8')
        existing = {item['category'] for item in findings if item['location'] == location}
        for category, pattern in COMPILED.items():
            if category not in existing and pattern.search(decoded):
                finding(findings, location, category)
    except (ValueError, UnicodeDecodeError):
        pass
    except RecursionError:
        finding(findings, location, 'unreadable_file')

    suffix = expected.lower()
    is_gzip = data.startswith(b'\x1f\x8b')
    is_zip = data.startswith((b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'))
    is_tar = len(data) > 262 and data[257:262] == b'ustar'
    looks_gzip = suffix.endswith(('.gz', '.tgz'))
    looks_zip = suffix.endswith('.zip')
    looks_tar = suffix.endswith('.tar')
    try:
        if is_gzip:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                content = stream.read(LIMIT + 1)
            inner = suffix[:-3] + '.tar' if suffix.endswith('.tgz') else suffix[:-3]
            scan(content, location + '!gzip', findings, depth + 1, budget, inner)
        elif is_zip:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                for i, item in enumerate(archive.infolist()):
                    loc = location + '!member_' + str(i)
                    if not budget.member():
                        finding(findings, loc, 'unscanned_limit')
                        break
                    scan(item.filename.encode('utf-8', 'surrogatepass'), loc + '!name', findings, depth + 1, budget)
                    if item.is_dir():
                        continue
                    if item.file_size > LIMIT:
                        finding(findings, loc, 'unscanned_limit')
                        continue
                    # ZIP symlink targets are member data and must be scanned too.
                    with archive.open(item) as stream:
                        content = stream.read(LIMIT + 1)
                    scan(content, loc, findings, depth + 1, budget, item.filename)
        elif is_tar or looks_tar:
            with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
                for i, item in enumerate(archive):
                    loc = location + '!member_' + str(i)
                    if not budget.member():
                        finding(findings, loc, 'unscanned_limit')
                        break
                    scan(item.name.encode('utf-8', 'surrogateescape'), loc + '!name', findings, depth + 1, budget)
                    metadata = '\n'.join([item.uname, item.gname] +
                        [str(k) + '=' + str(v) for k, v in item.pax_headers.items()])
                    scan(metadata.encode('utf-8', 'surrogateescape'), loc + '!metadata', findings, depth + 1, budget)
                    if item.issym() or item.islnk():
                        scan(item.linkname.encode('utf-8', 'surrogateescape'), loc + '!link', findings, depth + 1, budget)
                    elif item.isfile():
                        if item.size > LIMIT:
                            finding(findings, loc, 'unscanned_limit')
                            continue
                        stream = archive.extractfile(item)
                        if stream is None:
                            finding(findings, loc, 'unreadable_archive')
                            continue
                        with stream:
                            scan(stream.read(LIMIT + 1), loc, findings, depth + 1, budget, item.name)
                    elif not item.isdir():
                        finding(findings, loc, 'unreadable_archive')
        elif looks_gzip or looks_zip:
            finding(findings, location, 'unreadable_archive')
    except (OSError, EOFError, ValueError, OverflowError, RuntimeError, tarfile.TarError, zipfile.BadZipFile, zlib.error):
        finding(findings, location, 'unreadable_archive')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def git_entries(root, commit=None):
    entries = {}
    if commit:
        records = git(root, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0')
        for record in filter(None, records):
            meta, name = record.split(b'\t', 1)
            mode, kind, oid = meta.split()
            entries[os.fsdecode(name)] = (mode.decode(), kind.decode(), oid.decode(), '0')
    else:
        records = git(root, 'ls-files', '--stage', '-z').split(b'\0')
        for record in filter(None, records):
            meta, name = record.split(b'\t', 1)
            mode, oid, stage = meta.split()
            name = os.fsdecode(name)
            # Preserve an unmerged stage even when more than one exists.
            if name not in entries or stage != b'0':
                entries[name] = (mode.decode(), 'blob', oid.decode(), stage.decode())
    return entries


def scan_repository(root, source='worktree', base=None, paths=(), commit=None, identities=()):
    if any(not identity.strip() for identity in identities):
        raise ValueError('an explicitly supplied identity cannot be empty')
    entries = git_entries(root, commit if source == 'commit' else None)
    if base:
        diff = ['diff', '--name-only', '--diff-filter=ACMRT', '-z']
        if source == 'index':
            diff += ['--cached', base]
        elif source == 'commit':
            diff += [base, commit]
        else:
            diff += [base]
        names = {os.fsdecode(x) for x in git(root, *diff).split(b'\0') if x}
        if source == 'index':
            # Git's diff-filter omits unresolved entries; those must fail closed.
            names.update(name for name, entry in entries.items() if entry[3] != '0')
    elif paths:
        names = {name for name in entries if any(name == p or name.startswith(p.rstrip('/') + '/') for p in paths)}
        # Explicit untracked files are useful for a worktree-only preflight.
        if source == 'worktree':
            names.update(p for p in paths if p not in entries and
                         ((root / p).is_file() or (root / p).is_symlink()))
    else:
        names = set(entries)
    if paths and base:
        names = {name for name in names if any(name == p or name.startswith(p.rstrip('/') + '/') for p in paths)}
    findings = []
    if paths and not base:
        for requested in paths:
            if not any(name == requested or name.startswith(requested.rstrip('/') + '/') for name in names):
                finding(findings, safe_location(requested, identities), 'unreadable_file')
    count = 0
    batch = None
    if source in ('index', 'commit'):
        batch = subprocess.Popen(['git', '-C', str(root), 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name in sorted(names):
            location = safe_location(name, identities)
            scan(os.fsencode(name), location + '!path', findings, budget=Budget(identities))
            if source == 'worktree':
                path = root / name
                try:
                    if path.is_symlink():
                        data = os.fsencode(os.readlink(path))
                    elif path.is_file():
                        if path.stat().st_size > LIMIT:
                            finding(findings, location, 'unscanned_limit')
                            continue
                        data = path.read_bytes()
                    else:
                        finding(findings, location, 'unreadable_file')
                        continue
                except OSError:
                    finding(findings, location, 'unreadable_file')
                    continue
            else:
                entry = entries.get(name)
                if entry is None:
                    finding(findings, location, 'unreadable_file')
                    continue
                mode, kind, oid, stage = entry
                if stage != '0':
                    finding(findings, location, 'unmerged_index')
                    continue
                if kind != 'blob' or mode == '160000':
                    finding(findings, location, 'unsupported_git_object')
                    continue
                batch.stdin.write((oid + '\n').encode())
                batch.stdin.flush()
                header = batch.stdout.readline().split()
                if len(header) != 3 or header[1] != b'blob':
                    finding(findings, location, 'unreadable_file')
                    continue
                size = int(header[2])
                if size > LIMIT:
                    remaining = size + 1
                    while remaining:
                        chunk = batch.stdout.read(min(remaining, 1024 * 1024))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                    finding(findings, location, 'unscanned_limit')
                    continue
                data = batch.stdout.read(size)
                delimiter = batch.stdout.read(1)
                if len(data) != size or delimiter != b'\n':
                    finding(findings, location, 'unreadable_file')
                    continue
            count += 1
            is_link = (root / name).is_symlink() if source == 'worktree' else entries[name][0] == '120000'
            scan(data, location, findings, expected='' if is_link else name, budget=Budget(identities))
    finally:
        if batch:
            batch.stdin.close()
            batch.stdout.close()
            if batch.wait() != 0:
                finding(findings, 'git-cat-file', 'unreadable_file')
    return {'status': 'PUBLIC_READY' if not findings else 'NOT_PUBLIC_READY',
            'source': source, 'base': base, 'files_selected': len(names),
            'files_scanned': count, 'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--index', action='store_true', help='scan actual staged index blobs')
    group.add_argument('--commit', help='scan blobs in this commit')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--base', help='scan only files changed relative to this ref')
    parser.add_argument('--deny-identity', action='append', default=[],
                        help='also fail on this personal identity (repeatable; never written to the report)')
    parser.add_argument('--output', type=Path)
    parser.add_argument('paths', nargs='*')
    args = parser.parse_args()
    if any(not identity.strip() for identity in args.deny_identity):
        parser.error('--deny-identity cannot be empty')
    source = 'index' if args.index else 'commit' if args.commit else 'worktree'
    try:
        result = scan_repository(args.root.resolve(), source, args.base, args.paths, args.commit, args.deny_identity)
    except (OSError, subprocess.CalledProcessError) as exc:
        result = {'status': 'NOT_PUBLIC_READY', 'source': source, 'files_selected': 0,
                  'files_scanned': 0, 'findings': [{'location': 'repository',
                  'category': 'unreadable_file', 'classification': 'NEEDS_REVIEW',
                  'status': 'UNVERIFIED'}], 'error_type': type(exc).__name__}
    output = json.dumps(result, indent=2, ensure_ascii=True) + '\n'
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end='')
    return int(result['status'] != 'PUBLIC_READY')


if __name__ == '__main__':
    sys.exit(main())
