# SPDX-License-Identifier: Apache-2.0
"""Verify fixed source inputs and retain call locations without private source text."""
import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect(path, relative, names):
    tree = ast.parse(path.read_text())
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or '']
            rows.extend({'kind': 'import', 'line': node.lineno, 'module': name} for name in modules)
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in names:
                rows.append({'kind': 'call', 'line': node.lineno, 'function': name})
    return {'path': relative, 'sha256': sha(path), 'bytes': path.stat().st_size,
            'locations': sorted(rows, key=lambda row: row['line'])}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ['sources', 'lock', 'python-source', 'deps', 'localpilot', 'output']:
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Use a fresh output file')
    lock = json.loads(args.lock.read_text())
    public = []
    for row in lock['files']:
        if row['status'] != 'PASSED':
            continue
        path = args.sources / row['path']
        if sha(path) != row['sha256']:
            raise SystemExit('Source drift: ' + str(path))
        public.append(row)
    private_sha = subprocess.check_output(['git', '-C', str(args.localpilot), 'rev-parse', 'HEAD'], text=True).strip()
    if private_sha != '9a21ebbe6621de43be6568b64433230c317eb81a':
        raise SystemExit('Use the fixed read-only LocalPilot snapshot')
    if subprocess.check_output(['git', '-C', str(args.localpilot), 'status', '--porcelain'], text=True):
        raise SystemExit('Private snapshot has changes; do not rewrite it')
    names = {'os.open', 'os.fstat', 'os.getuid', 'os.set_blocking', 'os.read', 'os.killpg',
             'fcntl.flock', 'subprocess.Popen', 'selectors.DefaultSelector', 'selector.select'}
    private = [inspect(args.localpilot / name, name, names) for name in [
        'agent/__init__.py', 'agent/commands.py', 'localpilot_api/service.py',
        'localpilot_service/security.py', 'localpilot_service/workspaces.py',
        'localpilot_service/cli.py', 'localpilot_service/protocol.py']]
    python = [inspect(args.python_source / name, name, names) for name in [
        'Lib/subprocess.py', 'Lib/selectors.py', 'Lib/socket.py', 'Lib/ssl.py']]
    pypdf = [inspect(args.deps / 'pypdf' / name, 'pypdf/' + name, names) for name in [
        '__init__.py', '_page.py', '_doc_common.py', 'filters.py', '_utils.py']]
    report = {'status': 'PASSED_SOURCE_AUDIT_ONLY', 'source_lock_sha256': sha(args.lock),
              'versions': {key: value for key, value in lock.items() if key != 'files'},
              'public_files': public, 'private_scope': 'metadata and call/import names only; no source text',
              'localpilot_commit': private_sha, 'localpilot_files': private,
              'cpython_files': python, 'pypdf_files': pypdf}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Verified', len(public), 'fixed public files and original Python/private source locations')

if __name__ == '__main__':
    main()
