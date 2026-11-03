# SPDX-License-Identifier: Apache-2.0
"""Inventory the source use= graph for the pinned, built xterm entry.

The graph traces source dependencies; it does not determine authorship or
license compatibility, and is not a replacement for tic's capability logic.
"""
import argparse
import hashlib
import json
import re
import tarfile
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--terminfo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'src/ports/ncurses/source_lock.json').read_text())
    archive = args.archive.resolve(strict=True)
    build = args.terminfo.resolve(strict=True)
    receipt = json.loads((build / 'receipt.json').read_text())
    if sha(archive.read_bytes()) != lock['archive_sha256'] or receipt['source_sha256'] != lock['archive_sha256']:
        raise SystemExit('source archive hash mismatch')
    with tarfile.open(archive) as tar:
        source = tar.extractfile('ncurses-6.5/misc/terminfo.src').read()
    if sha(source) != receipt['terminfo_source_sha256'] or sha((build / 'terminfo/x/xterm').read_bytes()) != receipt['entry_sha256']:
        raise SystemExit('terminfo source or built entry hash mismatch')
    entries = {}
    current = None
    for number, line in enumerate(source.decode('utf-8').splitlines(), 1):
        if line and not line[0].isspace() and not line.startswith('#') and line.rstrip().endswith(','):
            aliases = line.split(',', 1)[0].split('|')
            current = {'line': number, 'header': line, 'use': []}
            for alias in aliases[:-1]:
                entries.setdefault(alias, []).append(current)
        elif current is not None and line[:1].isspace() and not line.lstrip().startswith('#'):
            current['use'].extend(re.findall(r'(?:^|[,\s])use=([^,\s]+)', line))
    queue, nodes = deque(['xterm']), {}
    while queue:
        name = queue.popleft()
        if name in nodes:
            continue
        options = entries.get(name, [])
        if len(options) != 1:
            raise SystemExit(f'entry {name!r} is missing or ambiguous: {len(options)}')
        nodes[name] = options[0]
        queue.extend(options[0]['use'])
    result = {'status': 'source_graph_only_not_license_review', 'source_archive_sha256': lock['archive_sha256'],
              'terminfo_source_sha256': sha(source), 'xterm_entry_sha256': receipt['entry_sha256'],
              'entry_count': len(nodes), 'entries': nodes,
              'limitations': ['source dependencies do not establish authorship',
                              'inherited capabilities may be overridden or cancelled',
                              'generated binary was hash-checked but graph semantics were not independently recompiled']}
    if args.output.exists():
        raise SystemExit('output already exists')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'entries': len(nodes)}))


if __name__ == '__main__':
    main()
