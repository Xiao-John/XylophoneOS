#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that G1 diagnostics reject unsafe or unverified inputs before extraction."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/glibc_g1_probe.py'

with tempfile.TemporaryDirectory(prefix='xos_glibc_g1_test_') as temporary:
    root = Path(temporary)
    archive = root / 'not_glibc.tar.xz'
    archive.write_bytes(b'not the locked archive')
    output = root / 'output'
    run = subprocess.run([sys.executable, SCRIPT, '--archive', archive, '--output', output], capture_output=True, text=True)
    assert run.returncode != 0 and 'SHA-256 mismatch' in run.stderr
    assert not output.exists()
    run = subprocess.run([sys.executable, SCRIPT, '--archive', archive, '--output', output, '--diagnose-nptl'], capture_output=True, text=True)
    assert run.returncode != 0 and 'requires --hacker-mode' in run.stderr
    assert not output.exists()
    output.mkdir()
    (output/'keep').write_text('preserve')
    run = subprocess.run([sys.executable, SCRIPT, '--archive', archive, '--output', output], capture_output=True, text=True)
    assert run.returncode != 0 and 'new directory' in run.stderr
    assert (output/'keep').read_text() == 'preserve'
print('PASS G1 probe guards')
