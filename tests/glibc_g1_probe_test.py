#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that G1 diagnostics reject unsafe or unverified inputs before extraction."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/glibc_g1_probe.py'
sys.path.insert(0, str(ROOT / 'scripts'))
from glibc_g1_probe import clean_build_environment
poison = {'CPATH': '/untrusted', 'CFLAGS': '-bad', 'CC': 'bad', 'READELF': 'bad',
          'PATH': '/tools', 'BISON_PKGDATADIR': '/data'}
clean, removed = clean_build_environment(poison)
assert clean == {'PATH': '/tools', 'BISON_PKGDATADIR': '/data'}
assert removed == ['CC', 'CFLAGS', 'CPATH', 'READELF']
assert len(poison) == 6

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
    run = subprocess.run([sys.executable, SCRIPT, '--archive', archive, '--output', output, '--synthetic-abi-tag'], capture_output=True, text=True)
    assert run.returncode != 0 and 'requires --xos-backend' in run.stderr
    assert not output.exists()
    output.mkdir()
    (output/'keep').write_text('preserve')
    run = subprocess.run([sys.executable, SCRIPT, '--archive', archive, '--output', output], capture_output=True, text=True)
    assert run.returncode != 0 and 'new directory' in run.stderr
    assert (output/'keep').read_text() == 'preserve'
fragment = ROOT / 'src/ports/glibc/sysdeps/xos/preconfigure'
for machine, host_os, expected in (('x86_64/64', 'xos', 'yes'),
                                   ('x86_64/x32', 'xos', 'no'),
                                   ('x86_64/64', 'linux-gnu', 'no'),
                                   ('x86_64/64', 'xos-unknown', 'no'),
                                   ('aarch64', 'xos', 'no')):
    run = subprocess.run(['sh', '-c', '. "$1"; printf %s "$libc_config_ok"',
                          'preconfigure-test', str(fragment)],
                         env={'machine': machine, 'host_os': host_os, 'libc_config_ok': 'no'},
                         capture_output=True, text=True, check=True)
    assert run.stdout == expected
print('PASS G1 probe guards and backend target selection')
