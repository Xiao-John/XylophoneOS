#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Redact host-private path tokens in historical evidence files.

Only path tokens are rewritten; hashes, statuses and command structure stay
untouched. Raw logs remain in the private workspace; the committed evidence
uses portable placeholders. Binary archives are not modified (that would
change their pinned hashes); they are reported for a separate policy decision.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Longest prefixes first so /private/tmp is not eaten by a shorter rule.
RULES = [
    (re.compile(r'(?i)/Users/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/home/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/private/tmp/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/var/folders/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/opt/homebrew/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/Library/Frameworks/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/workspace/scratch/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)/opt/codex/runtimes/[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
    (re.compile(r'(?i)[A-Za-z]:\\+Users\\+[^\s"\'<>,;)\]}]*'), '${XOS_LOCAL_PATH}'),
]

HASH = re.compile(r'\b[0-9a-f]{40,64}\b')
TEXT_SUFFIXES = {'.json', '.md', '.txt', '.log', '.sh', '.c', '.cpp', '.h', '.hpp', '.py'}


def normalize(text):
    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='rewrite files (default: dry run)')
    parser.add_argument('paths', nargs='*', type=Path,
                        help='files or directories (default: docs/reports)')
    args = parser.parse_args()
    targets = args.paths or [ROOT / 'docs/reports']
    changed = []
    skipped = []
    for target in targets:
        files = [target] if target.is_file() else sorted(target.rglob('*'))
        for path in files:
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                if path.is_file():
                    skipped.append(path)
                continue
            try:
                original = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                skipped.append(path)
                continue
            updated = normalize(original)
            if updated == original:
                continue
            if HASH.findall(original) != HASH.findall(updated):
                raise SystemExit(f'refusing to change hashes in {path}')
            changed.append(path)
            print(('write ' if args.write else 'would change ') + str(path.relative_to(ROOT)))
            if args.write:
                path.write_text(updated, encoding='utf-8')
    print(f'{len(changed)} file(s), {len(skipped)} binary/skipped')
    if skipped:
        print('binary/skipped (not modified):')
        for path in skipped[:20]:
            print('  ' + str(path.relative_to(ROOT)))


if __name__ == '__main__':
    main()
