#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory COW-sensitive kernel write sites at the frozen COW0 baseline.

A lexical inventory supports review; it does not prove absence of aliases,
assembly, DMA, indirect writes, or future paths. Reclassify every hit manually.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/reports/cow0_20261112/source_audit.json'
BASELINE = '9c51eb46e321e0f2aee7837b00e90d5733ad9cfb'
REVIEWED = (
    'src/kernel/core/memory.cpp', 'src/kernel/core/vm_pin.hpp',
    'src/kernel/core/vm_continuation.hpp', 'src/kernel/core/anonymous_reservations.hpp',
    'src/kernel/include/xos/memory.hpp', 'src/kernel/arch/x86_64/paging.cpp',
    'src/kernel/arch/x86_64/tasks.cpp', 'src/kernel/arch/x86_64/display_tasks.inc',
    'src/kernel/arch/x86_64/exceptions.cpp',
    'src/shared/include/xos/ipc_v1_abi.hpp', 'src/shared/include/xos/process_abi.hpp',
    'src/shared/include/xos/thread_abi.hpp',
)
DIRECT = re.compile(r'reinterpret_cast\s*<\s*(?:u8|u64|void)\s*\*\s*>\s*\(\s*physical\b')
COPYOUT = re.compile(r'\bcopy_to_user\s*\(')
DEFINITION = re.compile(r'^\s*(?:inline\s+)?void\s+copy_to_user\s*\(')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    files = sorted(path for path in (ROOT / 'src/kernel').rglob('*')
                   if path.is_file() and path.suffix in ('.cpp', '.hpp', '.inc', '.h'))
    hits = []
    for path in files:
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            kinds = []
            if COPYOUT.search(line) and not DEFINITION.search(line):
                kinds.append('copy_to_user')
            if DIRECT.search(line):
                kinds.append('physical_direct_candidate')
            if kinds:
                hits.append({'path': path.relative_to(ROOT).as_posix(), 'line': number,
                             'kinds': kinds, 'text': line.strip()})
    paths = sorted(set(REVIEWED) | {entry['path'] for entry in hits})
    return {'baseline_commit': BASELINE,
            'scope': 'lexical kernel user-copy and physical-write candidates; manual review required',
            'files_sha256': {path: sha(ROOT / path) for path in paths}, 'sites': hits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    current = inventory()
    serialized = json.dumps(current, ensure_ascii=False, indent=2) + '\n'
    if args.write:
        for path, digest in current['files_sha256'].items():
            original = subprocess.run(['git', 'show', f'{BASELINE}:{path}'], cwd=ROOT,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if original.returncode or hashlib.sha256(original.stdout).hexdigest() != digest:
                print(f'{path} differs from the declared baseline; review and select a new baseline',
                      file=sys.stderr)
                return 1
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(serialized, encoding='utf-8')
    elif args.check:
        if not OUTPUT.exists() or json.loads(OUTPUT.read_text(encoding='utf-8')) != current:
            print('COW0 source inventory differs: review changed/new write sites and refresh the contract', file=sys.stderr)
            return 1
        print(f"PASS COW0 source inventory: {len(current['sites'])} candidates; {len(current['files_sha256'])} files")
    else:
        print(serialized, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
