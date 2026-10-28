#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify and prepare a private QtBase source tree; never overwrite a tree."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

here = Path(__file__).resolve().parent
lock = json.loads((here / 'source_lock.json').read_text())
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('archive', type=Path)
p.add_argument('destination', type=Path, help='new directory for extracted QtBase')
a = p.parse_args()
if hashlib.sha256(a.archive.read_bytes()).hexdigest() != lock['sha256']:
    raise SystemExit('QtBase source SHA-256 mismatch')
if a.destination.exists() or a.destination.is_symlink():
    raise SystemExit('destination already exists; refusing to overwrite')
a.destination.mkdir(parents=True)
with tarfile.open(a.archive, 'r:xz') as archive:
    # Strip exactly one archive root, while rejecting absolute paths, traversal,
    # and links; upstream archive is fixed and integrity verified above.
    root = 'qtbase-everywhere-src-6.8.3/'
    for member in archive:
        if member.name == root.rstrip('/') and member.isdir():
            continue
        if not member.name.startswith(root):
            raise SystemExit('unexpected archive root: ' + member.name)
        relative = Path(member.name[len(root):])
        if relative == Path('.'):
            continue
        if relative.is_absolute() or '..' in relative.parts or member.issym() or member.islnk():
            raise SystemExit('unsafe archive member: ' + member.name)
        member.name = str(relative)
        archive.extract(member, path=a.destination, filter='data')
subprocess.run(['patch', '-p1', '-i', str(here / 'patches/0001-xos-platform-detection.patch')],
               cwd=a.destination, check=True)
shutil.copytree(here / 'mkspecs/xos-g++', a.destination / 'mkspecs/xos-g++')
print('Prepared verified QtBase source:', a.destination)
