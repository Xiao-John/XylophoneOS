#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the G1 dependency boundary, including hostile paths."""
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from glibc_g1_deps import collect_dependency_files

with tempfile.TemporaryDirectory(prefix='xos_glibc_deps_') as tmp:
    base = Path(tmp)
    source, build, compiler = base/'src', base/'build', base/'gcc/include'
    for directory in (source/'nptl', build/'nptl', compiler):
        directory.mkdir(parents=True)
    obj = build/'nptl/unit.o'
    obj.write_bytes(b'object')
    (source/'nptl/unit.c').write_bytes(b'source')
    (build/'config.h').write_bytes(b'config')
    (compiler/'stddef.h').write_bytes(b'compiler')
    dep = base/'unit.d'
    dep.write_text(f'$(common-objpfx)nptl/unit.o: unit.c $(common-objpfx)config.h {compiler}/stddef.h\n')
    collect = lambda: collect_dependency_files(dep, source, build, compiler, 'unit')
    try:
        collect_dependency_files(dep, source, build, compiler, 'other')
    except ValueError:
        pass
    else:
        raise AssertionError('accepted a dependency file for another object')
    before = collect()
    assert set(before) == {'source/nptl/unit.c', 'build/config.h', 'compiler/stddef.h'}
    (build/'config.h').write_bytes(b'tampered')
    assert collect() != before
    foreign = base/'foreign.h'
    foreign.write_text('newlib or host')
    for invalid in (str(foreign), '$(unknown)/foreign.h'):
        dep.write_text(f'{obj}: unit.c {invalid}\n')
        try:
            collect()
        except ValueError:
            pass
        else:
            raise AssertionError('accepted unexpected dependency: ' + invalid)
    link = source/'nptl/escape.h'
    link.symlink_to(foreign)
    dep.write_text(f'{obj}: unit.c escape.h\n')
    try:
        collect()
    except ValueError:
        pass
    else:
        raise AssertionError('accepted escaping symlink')
print('PASS dependency roots, generated-header binding and foreign input rejection')
