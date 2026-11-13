#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce an isolated glibc XOS configuration investigation (not a build)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new private research directory')
    parser.add_argument('--hacker-mode', action='store_true', help='diagnostic only: bypass upstream unsupported-platform guard')
    parser.add_argument('--diagnose-nptl', action='store_true', help='diagnostic only: use an empty XOS marker and synthetic ABI tag to expose NPTL dependencies')
    args = parser.parse_args()
    if args.diagnose_nptl and not args.hacker_mode:
        parser.error('--diagnose-nptl requires --hacker-mode')
    archive = args.archive.resolve(strict=True)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new directory')
    lock = json.loads((ROOT / 'src/ports/glibc/source_lock.json').read_text())
    if digest(archive) != lock['archive_sha256']:
        raise SystemExit('candidate source archive SHA-256 mismatch')
    output.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(output, filter='data')
    source = output / ('glibc-' + lock['version'])
    patch = ROOT / 'src/ports/glibc/patches/0001-config-sub-xos.patch'
    subprocess.run(['patch', '-p1', '-i', str(patch)], cwd=source, check=True)
    if args.diagnose_nptl:
        marker = source / 'sysdeps/xos'
        marker.mkdir()
        (marker / 'Implies').write_text('nptl\n')
        # This value is deliberately synthetic and is never an XOS ABI assignment.
        with (source / 'abi-tags').open('a') as file:
            file.write('\n.*-.*-xos.* 255 0.0.0\n')
    target = subprocess.check_output([source/'scripts/config.sub', 'x86_64-unknown-xos'], text=True).strip()
    build = output / 'configure'
    build.mkdir()
    command = [str(source/'configure'), '--build=aarch64-apple-darwin', '--host=x86_64-unknown-xos', '--disable-werror']
    if args.hacker_mode:
        command.append('--enable-hacker-mode')
    env = os.environ.copy()
    env['CC'] = 'x86_64-elf-gcc'
    env['CXX'] = 'x86_64-elf-g++'
    compiler_target = subprocess.check_output([env['CC'], '-dumpmachine'], text=True).strip()
    with (output/'configure.log').open('w') as log:
        result = subprocess.run(command, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
    make_result = None
    if args.diagnose_nptl and result.returncode == 0:
        with (output/'make.log').open('w') as log:
            make_result = subprocess.run(['gnumake', '-j4'], cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
    report = {'status': 'diagnostic_only', 'source_sha256': digest(archive),
              'source_authentication': lock['signature_verification'], 'patch_sha256': digest(patch),
              'canonical_target': target, 'command': command, 'cc': env['CC'],
              'cxx': env['CXX'], 'compiler_target': compiler_target,
              'hacker_mode': args.hacker_mode, 'configure_exit_code': result.returncode,
              'synthetic_nptl_diagnostic': args.diagnose_nptl,
              'configure_log_sha256': digest(output/'configure.log'),
              'not_claimed': ['XOS sysdeps', 'target runtime', 'guest qualification', 'distributable source']}
    if make_result is not None:
        report['make_exit_code'] = make_result.returncode
        report['make_log_sha256'] = digest(output/'make.log')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    # A synthetic backend is never a successful G1 configuration, even if
    # upstream configure and make happen to accept the temporary placeholders.
    if args.diagnose_nptl:
        return result.returncode or (make_result.returncode if make_result is not None else 1) or 1
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())
