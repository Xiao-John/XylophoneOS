#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the narrowly scoped, incomplete G1 diagnostic build artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    report = json.loads((output / 'report.json').read_text())
    assert report['status'] == 'diagnostic_only' and report['synthetic_nptl_diagnostic']
    assert report['sysroot_enforced'] and report['configure_exit_code'] == 0
    assert report['make_exit_code'] != 0 and report['header_install']['exit_code'] != 0
    source = output / 'glibc-2.44'
    build = output / 'configure'
    compiler = Path(report['compiler_path']).resolve(strict=True)
    assert digest(compiler) == report['compiler_sha256']
    compiler_include = Path(subprocess.check_output([str(compiler), '-print-file-name=include'], text=True).strip()).resolve()
    roots = (source.resolve(), build.resolve(), compiler_include, compiler_include.parent / 'include-fixed')
    for subdir, name, implementation in (('stdlib', 'abs', 'stdlib/abs.c'),
                                          ('posix', '_exit', 'sysdeps/xos/_exit.c')):
        artifact = build / subdir / (name + '.o')
        item = report['diagnostic_objects'][name]
        assert item['exit_code'] == 0 and digest(artifact) == item['sha256']
        output_text = (output / (name + '-readelf.txt')).read_text()
        assert 'ELF64' in output_text and 'Advanced Micro Devices X86-64' in output_text
        assert re.search(r'\bFUNC\s+GLOBAL\s+\w+\s+\d+\s+' + name + r'\s*$', output_text, re.M)
        dep = output / (name + '-dependencies.d')
        assert digest(dep) == item['dependency_file_sha256']
        first_rule = dep.read_text().replace('\\\n', ' ').splitlines()[0]
        inputs = shlex.split(first_rule.split(':', 1)[1])
        resolved = [(source / subdir / name).resolve(strict=True) for name in inputs]
        assert (source / implementation).resolve() in resolved
        for path in resolved:
            assert any(path == root or root in path.parents for root in roots), f'unexpected header: {path}'
    text = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'posix/_exit.o')], text=True)
    assert re.search(r'\bmov\s+\$0x2,%eax', text) and re.search(r'\bint\s+\$0x80', text)
    assert re.search(r'\bud2\b', text) and not re.search(r'R_X86_64_', text)
    root = output / 'xos-glibc-sysroot'
    manifest = json.loads((output / 'header-manifest.json').read_text())
    assert digest(output / 'header-manifest.json') == report['header_install']['manifest_sha256']
    assert len(manifest) == report['header_install']['file_count']
    assert set(manifest) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    for name, expected in manifest.items():
        assert digest(root / name) == expected
    assert digest(root / 'usr/include/stdlib.h') == digest(source / 'stdlib/stdlib.h')
    assert digest(root / 'usr/include/bits/stdio_lim.h') == digest(source / 'sysdeps/xos/bits/stdio_lim.h')
    assert 'bits/semaphore.h' in (output / 'install-headers.log').read_text()
    print('PASS diagnostic objects, symbols, instruction sequence, header provenance and partial sysroot')
    print('NOT ACCEPTED: synthetic backend setup, incomplete headers and libc build, no guest test')


if __name__ == '__main__':
    main()
