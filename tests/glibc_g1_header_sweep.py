#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diagnose installed public headers with glibc's build-only stub placeholder."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--language', choices=('c', 'c++'), default='c')
args = parser.parse_args()
output = args.output.resolve(strict=True)
report_path = output/'report.json'
report_sha = digest(report_path)
report = json.loads(report_path.read_text())
assert report['header_bootstrap_client']['diagnostic_only'] and report['sysroot_enforced']
sysroot = output/'xos-glibc-sysroot'
root = sysroot/'usr/include'
manifest_path = output/'header-manifest.json'
manifest_sha = digest(manifest_path)
assert manifest_sha == report['header_install']['manifest_sha256']
manifest = json.loads(manifest_path.read_text())
placeholder = (output/'header-bootstrap/gnu/stubs.h').resolve(strict=True)
assert digest(placeholder) == report['header_bootstrap_client']['placeholder_sha256']
assert not (root/'gnu/stubs.h').exists()
compiler_info = report['tools']['x86_64-elf-gcc' if args.language == 'c' else 'x86_64-elf-g++']
compiler = Path(compiler_info['path']).resolve(strict=True)
assert digest(compiler) == compiler_info['sha256']
compiler_include = Path(subprocess.check_output([str(compiler), '-print-file-name=include'], text=True).strip()).resolve(strict=True)
headers = sorted(p.relative_to(root).as_posix() for p in root.rglob('*.h')
                 if p.relative_to(root).parts[0] not in ('bits', 'gnu', 'finclude') and p.name != 'regexp.h')
results = {}
with tempfile.TemporaryDirectory(prefix='xos_glibc_headers_') as tmp:
    depfile = Path(tmp)/'deps.d'
    for header in headers:
        cmd = [str(compiler), '--sysroot='+str(sysroot), '-isystem', str(output/'header-bootstrap'),
               '-isystem', str(root), '-ffreestanding', '-fsyntax-only', '-MD', '-MF', str(depfile),
               '-MT', 'probe', '-x', args.language, '-']
        if args.language == 'c++':
            cmd[1:1] = ['-std=c++17', '-nostdinc++']
        run = subprocess.run(cmd, input='#include <'+header+'>\n', text=True, capture_output=True)
        inputs = {}
        if run.returncode == 0:
            rule = depfile.read_text().replace('\\\n', ' ').splitlines()[0]
            for item in shlex.split(rule.split(':', 1)[1]):
                path = Path(item).resolve(strict=True)
                if root.resolve() in path.parents:
                    key = 'usr/include/'+path.relative_to(root.resolve()).as_posix()
                    assert key in manifest and digest(path) == manifest[key], path
                else:
                    assert path == placeholder or compiler_include in path.parents, path
                inputs[str(path)] = digest(path)
            assert (root/header).resolve() in map(Path, inputs)
        results[header] = {'exit_code': run.returncode, 'error': run.stderr[-2000:] if run.returncode else '',
                           'dependencies': inputs}
failed = [name for name, result in results.items() if result['exit_code']]
assert digest(placeholder) == report['header_bootstrap_client']['placeholder_sha256']
assert digest(compiler) == compiler_info['sha256']
assert digest(report_path) == report_sha and digest(manifest_path) == manifest_sha
result = {'status': 'diagnostic_only', 'placeholder': True, 'language': args.language,
          'source_report_sha256': report_sha, 'manifest_sha256': manifest_sha,
          'sweep_sha256': digest(Path(__file__)),
          'compiler_sha256': digest(compiler), 'total': len(headers), 'failed': failed, 'headers': results}
(output/('header-sweep.json' if args.language == 'c' else 'header-sweep-cxx.json')).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({'total': len(headers), 'failed': failed}, ensure_ascii=False))
