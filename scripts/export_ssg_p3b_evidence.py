#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create and scan a sanitized local candidate; never uploads anything."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from ssg_public_paths import portable
import check_public_evidence_paths as scanner


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scan_blob(data, name):
    findings = []
    scanner.scan(data, name, findings, budget=scanner.Budget([Path.home().name]), expected=name)
    if findings:
        raise ValueError('public scan failed for ' + name + ': ' + ','.join(x['category'] for x in findings))


def scan_encoded_records(data, label):
    patterns = [
        ('p3b', re.compile(rb'^P3B_FRAME_(BEGIN|PART|END) (\S+) (\S+) (\d+)(?: (.*))?$')),
        ('ssg', re.compile(rb'^SSG_FRAME_(BEGIN|PART|END) (REQ|RESP|TEXT) (\d+)(?: (.*))?$')),
        ('oracle', re.compile(rb'^SSG_ORACLE_(BEGIN|PART|END) (\d+)(?: (.*))?$')),
    ]
    pending = {}
    for line in data.splitlines():
        parsed = None
        for typ, pattern in patterns:
            match = pattern.fullmatch(line)
            if match:
                parsed = (typ, list(match.groups()))
                break
        if not parsed:
            if any(marker in line for marker in (b'P3B_FRAME_', b'SSG_FRAME_', b'SSG_ORACLE_')):
                raise ValueError('malformed encoded record in ' + label)
            continue
        typ, groups = parsed
        kind = groups.pop(0)
        if typ == 'p3b':
            slot, direction, seq, tail = groups
            key = (typ, slot, direction, seq)
        elif typ == 'ssg':
            direction, seq, tail = groups
            key = (typ, direction, seq)
        else:
            seq, tail = groups
            key = (typ, seq)
        if kind == b'BEGIN':
            if key in pending or tail is None:
                raise ValueError('duplicate or malformed encoded record in ' + label)
            size, encoded = map(int, tail.split())
            pending[key] = [size, encoded, bytearray()]
        elif kind == b'PART':
            if key not in pending or tail is None:
                raise ValueError('orphan encoded record in ' + label)
            offset, chunk = tail.split(b' ', 1)
            if int(offset) != len(pending[key][2]):
                raise ValueError('non-contiguous encoded record in ' + label)
            pending[key][2].extend(chunk)
        else:
            if key not in pending or tail is not None:
                raise ValueError('orphan record end in ' + label)
            size, encoded, contents = pending.pop(key)
            if len(contents) != encoded:
                raise ValueError('incomplete encoded record in ' + label)
            payload = base64.b64decode(contents, validate=True)
            if len(payload) != size:
                raise ValueError('invalid encoded record size in ' + label)
            scan_blob(payload, label + '-decoded.json')
    if pending:
        raise ValueError('unfinished encoded record in ' + label)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prefix', required=True, help='run prefix such as v10')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--qemu', type=Path, required=True)
    p.add_argument('--sdk', type=Path, required=True)
    p.add_argument('--qt-build', type=Path, required=True)
    p.add_argument('--qt-source', type=Path, required=True)
    p.add_argument('--host-qt', type=Path, required=True)
    p.add_argument('--binutils', type=Path, required=True)
    p.add_argument('--dash', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = ROOT / 'build/p3b'
    build = base / a.prefix
    mappings = [('XOS_IMAGE', a.image), ('XOS_QEMU', a.qemu), ('XOS_SDK_PREFIX', a.sdk),
                ('XOS_BUILD_DIR', a.qt_build), ('XOS_QT_SOURCE', a.qt_source), ('XOS_HOST_QT', a.host_qt),
                ('XOS_BINUTILS', a.binutils), ('XOS_DASH_ELF', a.dash), ('XOS_P3B_BUILD_DIR', build),
                ('XOS_TEMP_ROOT', tempfile.gettempdir()), ('XOS_PYTHON', sys.executable)]
    exported = {'archives': {}, 'loose_files': {}, 'skipped_missing': []}

    def transform(path):
        raw = path.read_bytes()
        if path.suffix == '.json':
            obj = json.loads(raw)
            if isinstance(obj, dict):
                obj.pop('traceback', None)
            content = (json.dumps(portable(obj, mappings, strict=True), indent=2, ensure_ascii=False) + '\n').encode()
        else:
            content = raw
        scan_blob(content, path.name)
        if path.name.endswith('serial.log'):
            scan_encoded_records(content, path.name)
        return raw, content

    def archive(label, folder):
        if not folder.is_dir():
            exported['skipped_missing'].append(label)
            return
        chosen = []
        for file in sorted(folder.rglob('*')):
            if not file.is_file() or file.is_symlink():
                continue
            name = file.name
            if (name.endswith('serial.log') or name == 'guest_qemu.log' or
                name == 'synthetic-input.txt' or
                name.endswith(('.json', '.wire', '.bin', '.html', '.png', '.ppm'))):
                chosen.append(file)
        entries = {}
        memory = io.BytesIO()
        with tarfile.open(fileobj=memory, mode='w:gz', format=tarfile.PAX_FORMAT) as tar:
            for file in chosen:
                member = str(file.relative_to(folder))
                raw, content = transform(file)
                entries[member] = {'raw_sha256': sha(raw), 'exported_sha256': sha(content),
                                   'transformation': 'unchanged' if raw == content else 'portable-json-and-omitted-traceback'}
                info = tarfile.TarInfo(member)
                info.size = len(content);info.mtime = 0;info.mode = 0o644;info.uid = info.gid = 0;info.uname = info.gname = ''
                tar.addfile(info, io.BytesIO(content))
            manifest = (json.dumps({'members': entries}, indent=2) + '\n').encode()
            info = tarfile.TarInfo('export-manifest.json');info.size = len(manifest);info.mtime = 0;info.mode = 0o644;info.uid = info.gid = 0;info.uname = info.gname = ''
            tar.addfile(info, io.BytesIO(manifest))
        data = memory.getvalue()
        scan_blob(data, label + '.tar.gz')
        (out / (label + '.tar.gz')).write_bytes(data)
        exported['archives'][label] = {'sha256': sha(data), 'members': len(entries)}

    cases = ('baseline', 'ordinary', 'ordinary-sample', 'ordinary-plain', 'default-denied', 'ordinary-default-denied', 'notes-denied', 'browser-denied', 'edit', 'revoke',
             'protect-document', 'protect-ancestor', 'browser-revoke', 'browser-reload', 'browser-scroll',
             'pipe-isolation', 'notes-exit', 'browser-exit', 'browser-exit-during-notes', 'notes-timeout', 'notes-truncated', 'notes-cancel',
             'restart', 'diff-contract', 'stress')
    for label in cases:
        archive(label, base / (a.prefix + '-' + label))
    for folder in sorted(base.glob(a.prefix + '-reg-*')):
        if folder.is_dir(): archive(folder.name.removeprefix(a.prefix + '-'), folder)
    # Preserve selected actual failures; their raw serials remain local too.
    for label, folder in (('failure-exclusive-surface', base / 'guest-attempt1'),
                          ('failure-unsaved-exit', base / 'v3-edit'),
                          ('failure-missing-owner-digest', base / 'v4-browser-denied')):
        archive(label, folder)
    for relative in ('manifest.json', 'browser-test/browser.portable.receipt.json', 'browser/browser.portable.receipt.json',
                     'notes-test/notes.receipt.json', 'notes/notes.receipt.json', 'aggregate-test/ssg-multi.receipt.json',
                     'aggregate/ssg-multi.receipt.json', 'consumer/ssg-consumer.receipt.json',
                     'consumer-test/ssg-consumer.receipt.json', 'boundaries/probe.receipt.json',
                     'aggregate-diff-test/probe.receipt.json'):
        file = build / relative
        if not file.is_file():
            exported['skipped_missing'].append('build-' + relative)
            continue
        raw, content = transform(file)
        name = 'build-' + relative.replace('/', '-')
        (out / name).write_bytes(content)
        exported['loose_files'][name] = {'raw_sha256': sha(raw), 'exported_sha256': sha(content)}
    data = (json.dumps(exported, indent=2) + '\n').encode()
    scan_blob(data, 'export-index.json')
    (out / 'export-index.json').write_bytes(data)
    print(json.dumps({'status': 'CANDIDATE_SCANNED', 'archives': len(exported['archives']),
                      'loose_files': len(exported['loose_files']), 'missing': exported['skipped_missing']}))


if __name__ == '__main__':
    main()
