#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export only selected synthetic watch evidence after recursive privacy scans."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from export_ssg_p3b_evidence import scan_blob, scan_encoded_records
from ssg_public_paths import portable


def digest(data):
    return hashlib.sha256(data).hexdigest()


def omit_tracebacks(value):
    if isinstance(value, dict):
        return {key: omit_tracebacks(item) for key, item in value.items() if key != 'traceback'}
    if isinstance(value, list):
        return [omit_tracebacks(item) for item in value]
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('cases', nargs='+', help='case directories directly under the results directory')
    a = p.parse_args()
    root = a.results.resolve(strict=True)
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    mappings = [('XOS_P3C_BUILD_DIR', a.build), ('XOS_P3C_RESULTS_DIR', root)]
    index = {'scope': 'synthetic guest-only data; raw local files remain local', 'archives': {}, 'loose_files': {}}

    def transform(path):
        raw = path.read_bytes()
        if path.suffix == '.json':
            value = omit_tracebacks(json.loads(raw))
            data = (json.dumps(portable(value, mappings, strict=True), indent=2, ensure_ascii=False) + '\n').encode()
        else:
            data = raw
        scan_blob(data, path.name)
        if path.name == 'serial.log':
            scan_encoded_records(data, path.name)
        return raw, data

    build_manifest = a.build / 'manifest.json'
    raw, data = transform(build_manifest)
    (out / 'build-manifest.json').write_bytes(data)
    index['loose_files']['build-manifest.json'] = {'raw_sha256': digest(raw), 'exported_sha256': digest(data)}
    allowed = {'serial.log', 'report.json', 'summary.json', 'comparison.json', 'independent-check.json', 'ordinary-check.json',
               'cancel-check.json', 'timeout-check.json', 'synthetic-input.txt', 'browser.receipt.json'}
    for name in a.cases:
        if '/' in name or name in ('.', '..'):
            raise ValueError('case must be a directory name')
        folder = (root / name).resolve(strict=True)
        if folder.parent != root or not folder.is_dir():
            raise ValueError('case is not directly under results root')
        files = sorted(path for path in folder.rglob('*') if path.is_file() and not path.is_symlink() and path.name in allowed)
        if not files:
            raise ValueError('case has no selected evidence: ' + name)
        memory = io.BytesIO()
        members = {}
        with tarfile.open(fileobj=memory, mode='w:gz', format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                member = str(path.relative_to(folder))
                raw, data = transform(path)
                members[member] = {'raw_sha256': digest(raw), 'exported_sha256': digest(data)}
                info = tarfile.TarInfo(member)
                info.size = len(data);info.mtime = 0;info.mode = 0o644;info.uid = info.gid = 0;info.uname = info.gname = ''
                archive.addfile(info, io.BytesIO(data))
            data = (json.dumps({'members': members}, indent=2) + '\n').encode()
            info = tarfile.TarInfo('export-manifest.json')
            info.size = len(data);info.mtime = 0;info.mode = 0o644;info.uid = info.gid = 0;info.uname = info.gname = ''
            archive.addfile(info, io.BytesIO(data))
        data = memory.getvalue()
        scan_blob(data, name + '.tar.gz')
        (out / (name + '.tar.gz')).write_bytes(data)
        index['archives'][name] = {'sha256': digest(data), 'members': len(members)}
        print('exported', name, flush=True)
    data = (json.dumps(index, indent=2) + '\n').encode()
    scan_blob(data, 'export-index.json')
    (out / 'export-index.json').write_bytes(data)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
