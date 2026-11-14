#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diagnose installed public headers with glibc's build-only stub placeholder."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
args = parser.parse_args()
output = args.output.resolve(strict=True)
report = json.loads((output/'report.json').read_text())
assert report['header_bootstrap_client']['diagnostic_only']
root = output/'xos-glibc-sysroot/usr/include'
manifest = json.loads((output/'header-manifest.json').read_text())
headers = sorted(p.relative_to(root).as_posix() for p in root.rglob('*.h')
                 if p.relative_to(root).parts[0] not in ('bits', 'gnu', 'finclude') and p.name != 'regexp.h')
results = {}
for header in headers:
    path = root/header
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['usr/include/'+header]
    cmd = [str(output/'cc'), '-isystem', str(output/'header-bootstrap'), '-isystem', str(root),
           '-ffreestanding', '-fsyntax-only', '-x', 'c', '-']
    result = subprocess.run(cmd, input='#include <'+header+'>\n', text=True, capture_output=True)
    results[header] = {'exit_code': result.returncode, 'error': result.stderr[-2000:] if result.returncode else ''}
failed = [name for name, result in results.items() if result['exit_code']]
result = {'status': 'diagnostic_only', 'placeholder': True, 'total': len(headers), 'failed': failed, 'headers': results}
(output/'header-sweep.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({'total': len(headers), 'failed': failed}, ensure_ascii=False))
