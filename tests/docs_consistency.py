# SPDX-License-Identifier: Apache-2.0
"""Check live document links, compressed-history provenance and ABI allocations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def live_markdown():
    files = [p for p in (ROOT / 'docs').rglob('*.md')
             if 'reports' not in p.relative_to(ROOT / 'docs').parts
             and ('releases' not in p.relative_to(ROOT / 'docs').parts or p.name == 'next_release.md')]
    tracked = subprocess.check_output(['git', 'ls-files', '--', 'AGENTS.md', 'README.md', 'src/ports'], text=True)
    files.extend(ROOT / p for p in tracked.splitlines() if p.endswith('.md'))
    return sorted(set(files))


def anchors(text):
    values = set(re.findall(r'<a\s+id="([^"]+)"', text))
    repeats = {}
    for heading in re.findall(r'^#{1,6}\s+(.+)', text, re.M):
        heading = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', heading)
        slug = ''.join(c for c in heading.lower() if c.isalnum() or c in ' _-')
        slug = slug.replace(' ', '-')
        count = repeats.get(slug, 0)
        repeats[slug] = count + 1
        values.add(slug + ('-' + str(count) if count else ''))
    return values


def check_links():
    failures = []
    checked = 0
    for path in live_markdown():
        text = re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', path.read_text(), flags=re.M | re.S)
        for href in re.findall(r'\]\(([^)\s]+)\)', text):
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', href):
                continue
            relative, _, fragment = unquote(href).partition('#')
            target = (path.parent / relative).resolve() if relative else path
            checked += 1
            if not target.exists():
                failures.append(f'{path.relative_to(ROOT)} -> {href}')
            elif fragment and target.suffix == '.md' and fragment not in anchors(target.read_text()):
                failures.append(f'{path.relative_to(ROOT)} -> missing anchor {href}')
    assert not failures, '\n'.join(failures)
    return checked


def check_registry():
    text = (ROOT / 'docs/contracts/abi_registry.md').read_text()
    rows = re.findall(r'^\| (\d+) \| `(sys_[a-z0-9_]+)` \| `([^`]+)` \|$', text, re.M)
    actual = {}
    paths = [ROOT / 'src/kernel/include/xos/syscall.hpp',
             *sorted((ROOT / 'src/shared/include/xos').glob('*abi.hpp'))]
    for path in paths:
        for name, value in re.findall(r'\b(sys_[a-z0-9_]+)\s*=\s*(\d+)', path.read_text()):
            number = int(value)
            assert number not in actual, (number, actual.get(number), name)
            actual[number] = (name, path.relative_to(ROOT).as_posix())
    documented = {}
    for value, name, path in rows:
        number = int(value)
        assert number not in documented, ('registry duplicate', number)
        documented[number] = (name, path)
    assert actual == documented, ('source/registry mismatch', actual.keys() ^ documented.keys(),
                                  {k: (actual.get(k), documented.get(k)) for k in actual.keys() | documented.keys()
                                   if actual.get(k) != documented.get(k)})
    bands = [(int(a), int(b), status) for a, b, status in
             re.findall(r'^\| (\d+) \| (\d+) \| (allocated|reserved|unallocated) \|', text, re.M)]
    assert bands and bands[0][0] == 0
    for i, (first, last, status) in enumerate(bands):
        assert first <= last
        if i:
            assert first == bands[i - 1][1] + 1, ('gap/overlap', bands)
        for number in actual:
            if first <= number <= last:
                assert status == 'allocated', ('unallocated syscall implemented', number, status)
    assert all(sum(a <= n <= b for a, b, _ in bands) == 1 for n in actual)
    claims = re.findall(r'^\| (\d+) \| `(sys_[a-z0-9_]+)` \| ([^|]+) \| claimed \| ([^|]+) \|$', text, re.M)
    claimed_numbers = set()
    claimed_names = set()
    for value, name, owner, implementation in claims:
        number = int(value)
        assert number not in actual and number not in claimed_numbers, ('claim conflict', number)
        assert name not in {entry[0] for entry in actual.values()} and name not in claimed_names
        assert owner.strip() and implementation.strip()
        assert any(a <= number <= b and status == 'reserved' for a, b, status in bands), number
        claimed_numbers.add(number)
        claimed_names.add(name)
    return len(rows)


def check_provenance():
    index = json.loads((ROOT / 'docs/history/source_index.json').read_text())
    seen = set()
    for row in index['sources']:
        assert row['path'] not in seen, row['path']
        seen.add(row['path'])
        original = subprocess.check_output(['git', 'show', index['source_commit'] + ':' + row['path']])
        assert hashlib.sha256(original).hexdigest() == row['sha256'], row['path']
        target, _, fragment = row['summary'].partition('#')
        path = ROOT / target
        assert path.exists(), row
        assert not fragment or fragment in anchors(path.read_text()), row
    return len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/docs_constitution')
    args = parser.parse_args()
    report = {'status': 'passed', 'local_links': check_links(),
              'allocated_syscalls': check_registry(), 'history_sources': check_provenance()}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'docs_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
