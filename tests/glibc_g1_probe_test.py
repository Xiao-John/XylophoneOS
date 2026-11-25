#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that G1 diagnostics reject unsafe or unverified inputs before extraction."""
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/glibc_g1_probe.py'
sys.path.insert(0, str(ROOT / 'scripts'))
from glibc_g1_probe import clean_build_environment, select_gnu_make
poison = {'CPATH': '/untrusted', 'CFLAGS': '-bad', 'CC': 'bad', 'READELF': 'bad',
          'MAKE': 'wrong-make', 'PATH': '/tools', 'BISON_PKGDATADIR': '/data'}
clean, removed = clean_build_environment(poison)
assert clean == {'PATH': '/tools', 'BISON_PKGDATADIR': '/data'}
assert removed == ['CC', 'CFLAGS', 'CPATH', 'MAKE', 'READELF']
assert len(poison) == 7

linux_make = {'path': '/usr/bin/make', 'version_exit_code': 0, 'version': 'GNU Make 4.4.1'}
mac_make = {'path': '/gnu/bin/gmake', 'version_exit_code': 0, 'version': 'GNU Make 4.4.1'}
old_make = {'path': '/usr/bin/make', 'version_exit_code': 0, 'version': 'GNU Make 3.81'}
with patch('glibc_g1_probe.tool_identity', side_effect=[linux_make]) as probe:
    assert select_gnu_make() == linux_make
    probe.assert_called_once_with('make')
with patch('glibc_g1_probe.tool_identity', side_effect=[old_make, mac_make]):
    assert select_gnu_make() == mac_make
with patch('glibc_g1_probe.tool_identity', side_effect=[old_make, {}, {}]):
    try:
        select_gnu_make()
    except SystemExit as error:
        assert 'GNU make 4 or later is required' in str(error)
    else:
        raise AssertionError('accepted obsolete or missing make')

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
