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
import sys
import tarfile
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve(strict=True)
    report = json.loads((output / 'report.json').read_text())
    root = Path(__file__).resolve().parents[1]
    lock = json.loads((root / 'src/ports/glibc/source_lock.json').read_text())
    assert digest(args.archive) == lock['archive_sha256'] == report['source_sha256']
    assert digest(root / 'scripts/glibc_g1_probe.py') == report['probe_sha256']
    assert digest(root / 'src/ports/glibc/patches/0001-config-sub-xos.patch') == report['patch_sha256']
    assert digest(root / 'src/ports/glibc/patches/0002-xos-abi-note.patch') == report['xos_abi_note_patch_sha256']
    assert digest(root / 'src/ports/glibc/patches/0003-xos-tls-init.patch') == report['xos_tls_patch_sha256']
    assert digest(root / 'src/ports/glibc/patches/0004-sigset-error-pointer.patch') == report['sigset_patch_sha256']
    for filename, key in (('0005-raise-hidden-alias.patch', 'raise_patch_sha256'),
                          ('0006-sigwait-failure.patch', 'sigwait_patch_sha256'),
                          ('0007-arc4random-atomic-include.patch', 'atomic_patch_sha256'),
                          ('0008-freopen-no-fd-path.patch', 'freopen_patch_sha256'),
                          ('0009-dlerror-errno-include.patch', 'dlerror_patch_sha256'),
                          ('0010-sem-init-private-only.patch', 'sem_init_patch_sha256'),
                          ('0011-nptl-explicit-includes.patch', 'nptl_include_patch_sha256'),
                          ('0012-socket-include-types.patch', 'socket_types_patch_sha256'),
                          ('0013-thread-db-sigset-include.patch', 'thread_db_patch_sha256'),
                          ('0014-xos-reserved-dtv.patch', 'dtv_patch_sha256')):
        assert digest(root / 'src/ports/glibc/patches' / filename) == report[key]
    assert report['status'] == 'diagnostic_only' and report['nptl_backend_experimental'] and not report['synthetic_abi_tag']
    assert report['sysroot_enforced'] and report['configure_exit_code'] == 0
    assert report['readelf'] == report['tools']['x86_64-elf-readelf']['path']
    assert 'readelf: command not found' not in (output / 'configure.log').read_text()
    assert "READELF='" + report['readelf'] + "'" in (output / 'configure/config.log').read_text()
    assert not report['hacker_mode'] and '--enable-hacker-mode' not in report['command']
    assert report['make_exit_code'] != 0 and report['header_install']['exit_code'] == 0
    assert report['header_client']['exit_code'] != 0
    make_log = output / 'make.log'
    assert digest(make_log) == report['make_log_sha256']
    first_error = next(
        (number, line) for number, line in enumerate(make_log.read_text().splitlines(), 1)
        if re.search(r'(^|:\s+)(fatal error|error|Error):', line))
    assert report['first_build_error'] == {'line': first_error[0], 'diagnostic': first_error[1]}
    cxx_probe = report['cxx_freestanding']
    assert cxx_probe['diagnostic_only'] and cxx_probe['exit_code'] == 0
    assert digest(output / 'cxx-freestanding.cc') == cxx_probe['source_sha256']
    assert digest(output / 'cxx-freestanding.o') == cxx_probe['object_sha256']
    assert digest(output / 'cxx-freestanding.log') == cxx_probe['log_sha256']
    cxx_elf = subprocess.check_output(['x86_64-elf-readelf', '--wide', '-h', '-s', str(output / 'cxx-freestanding.o')], text=True)
    assert 'Advanced Micro Devices X86-64' in cxx_elf and re.search(r'\bTLS\b.*\bcxx_tls\b', cxx_elf)
    source = output / 'glibc-2.44'
    build = output / 'configure'
    with tarfile.open(args.archive) as tar:
        original = tar.extractfile('glibc-2.44/stdlib/abs.c')
        assert original is not None and original.read() == (source / 'stdlib/abs.c').read_bytes()
    sysdirs = (build / 'config.make').read_text()
    selected = re.search(r'^config-sysdirs\s*=\s*(.+)$', sysdirs, re.M)[1].split()
    assert selected.index('sysdeps/x86_64/xos') < selected.index('sysdeps/x86_64/nptl')
    assert selected.index('sysdeps/xos') < selected.index('sysdeps/nptl')
    assert all('linux' not in directory.split('/') for directory in selected)
    assert 'experimental and incomplete' in (output / 'configure.log').read_text()
    assert not re.search(r'^\.\*-\.\*-xos', (source / 'abi-tags').read_text(), re.M)
    sys.path.insert(0, str(root / 'scripts'))
    from glibc_g1_deps import collect_dependency_files
    assert digest(root / 'scripts/glibc_g1_deps.py') == report['dependency_collector_sha256']
    dependency_manifest_path = output / 'dependency-manifest.json'
    assert digest(dependency_manifest_path) == report['dependency_manifest_sha256']
    dependency_manifest = json.loads(dependency_manifest_path.read_text())
    successful = {name for name, item in report['diagnostic_objects'].items() if item['exit_code'] == 0}
    assert set(dependency_manifest) == successful
    overlay = Path(__file__).resolve().parents[1] / 'src/ports/glibc/sysdeps'
    for name, expected in report['xos_overlay_sha256'].items():
        assert digest(overlay / name) == expected == digest(source / 'sysdeps' / name)
    assert set(report['xos_overlay_sha256']) == {str(p.relative_to(overlay)) for p in overlay.rglob('*') if p.is_file()}
    for tool in report['tools'].values():
        if tool['available']:
            assert digest(Path(tool['path'])) == tool['sha256']
    compiler = Path(report['compiler_path']).resolve(strict=True)
    assert digest(compiler) == report['compiler_sha256']
    compiler_include = Path(subprocess.check_output([str(compiler), '-print-file-name=include'], text=True).strip()).resolve()
    roots = (source.resolve(), build.resolve(), compiler_include, compiler_include.parent / 'include-fixed')
    # Reconstruct patched upstream files independently from the locked archive;
    # verify every compiler-consumed source and header, not just abs/_exit.
    patches = sorted((root / 'src/ports/glibc/patches').glob('*.patch'))
    patched_files = set()
    for patch in patches:
        for line in patch.read_text().splitlines():
            if line.startswith('+++ b/'):
                patched_files.add(line[6:])
    with tempfile.TemporaryDirectory(prefix='xos_glibc_pristine_') as temp:
        pristine = Path(temp)
        with tarfile.open(args.archive) as tar:
            for name in patched_files:
                source_file = tar.extractfile('glibc-2.44/' + name)
                assert source_file is not None
                destination = pristine / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source_file.read())
        for patch in patches:
            subprocess.run(['patch', '-s', '-p1', '-i', str(patch)], cwd=pristine, check=True)
        upstream = {}
        for name in sorted(successful):
            depfile = output / (name + '-dependencies.d')
            assert digest(depfile) == report['diagnostic_objects'][name]['dependency_file_sha256']
            inputs = collect_dependency_files(depfile, source, build, compiler_include, name)
            assert inputs == dependency_manifest[name]
            for key, expected in inputs.items():
                if not key.startswith('source/'):
                    continue
                relative = key[len('source/'):]
                if relative.startswith('sysdeps/') and (overlay / relative[len('sysdeps/'):]).is_file():
                    original = (overlay / relative[len('sysdeps/'):]).read_bytes()
                elif relative in patched_files:
                    original = (pristine / relative).read_bytes()
                else:
                    assert relative not in upstream or upstream[relative] == expected
                    upstream[relative] = expected
                    continue
                assert hashlib.sha256(original).hexdigest() == expected, relative
        with tarfile.open(args.archive, 'r|xz') as tar:
            for member in tar:
                prefix = 'glibc-2.44/'
                if member.name.startswith(prefix) and member.name[len(prefix):] in upstream:
                    relative = member.name[len(prefix):]
                    item = tar.extractfile(member)
                    assert item is not None and hashlib.sha256(item.read()).hexdigest() == upstream.pop(relative), relative
        assert not upstream, f'missing archive dependencies: {sorted(upstream)}'
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
        first_rule = first_rule.replace('$(common-objpfx)', str(build) + '/')
        first_rule = first_rule.replace('$(..)', str(source) + '/')
        inputs = shlex.split(first_rule.split(':', 1)[1])
        resolved = [(source / subdir / name).resolve(strict=True) for name in inputs]
        assert (source / implementation).resolve() in resolved
        for path in resolved:
            assert any(path == root or root in path.parents for root in roots), f'unexpected header: {path}'
    text = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'posix/_exit.o')], text=True)
    assert re.search(r'\bmov\s+\$0x2,%eax', text) and re.search(r'\bint\s+\$0x80', text)
    assert re.search(r'\bud2\b', text) and not re.search(r'R_X86_64_', text)
    assert digest(build / 'csu/abi-tag.h') == digest(source / 'sysdeps/xos/abi-tag.h')
    assert 'This configuration not matched in ../abi-tags' not in (output / 'make.log').read_text()
    note = report['diagnostic_objects']['abi-note']
    assert note['exit_code'] == 0 and report['isolated_abi_note'] is None
    assert digest(build / 'csu/abi-note.o') == note['sha256']
    assert digest(output / 'abi-note-readelf.txt') == note['notes_sha256']
    assert '../sysdeps/x86_64/xos/abi-note.c' in (output / 'abi-note-dependencies.d').read_text()
    notes = (output / 'abi-note-readelf.txt').read_text()
    assert 'NT_GNU_PROPERTY_TYPE_0' in notes and 'NT_GNU_ABI_TAG' not in notes
    for name, expected in report['generated_layout_headers'].items():
        assert digest(build / name) == expected
    assert '#define SEM_T_ALIGN 8' in (build / 'sem_t-align.h').read_text()
    assert '#define DTV_OFFSET 8' in (build / 'tlsdesc.h').read_text()
    deps = (build / 'tlsdesc.h.d').read_text()
    assert 'sysdeps/x86_64/xos/tls.h' in deps and 'sysdeps/x86_64/nptl/tls.h' in deps

    # Reuse glibc's actual compile flags, without a shell, to inspect the
    # deliberately failing TLS_INIT_TP hook in an XOS target object.
    logs = (output / 'abi-note-object.log').read_text() + (output / 'make.log').read_text()
    command_line = next(line for line in logs.splitlines()
                        if '/cc ../sysdeps/x86_64/xos/abi-note.c ' in line)
    cmd = shlex.split(command_line)
    position = cmd.index('../sysdeps/x86_64/xos/abi-note.c')
    cmd[position:position + 1] = ['-x', 'c', '-']
    for flag in ('-MF', '-MT'):
        if flag in cmd:
            position = cmd.index(flag)
            del cmd[position:position + 2]
    for flag in ('-MD', '-MP'):
        if flag in cmd:
            cmd.remove(flag)
    with tempfile.TemporaryDirectory(prefix='xos_glibc_tls_test_') as temp:
        obj = Path(temp) / 'tls_probe.o'
        cmd[cmd.index('-o') + 1] = str(obj)
        subprocess.run(cmd, cwd=source / 'csu', check=True, capture_output=True, text=True,
                       input='#include <tls.h>\nint tls_probe(void *p) { return TLS_INIT_TP(p); }\n')
        disassembly = subprocess.check_output(['x86_64-elf-objdump', '-d', str(obj)], text=True)
        assert re.search(r'\bxor\s+%eax,%eax', disassembly)
        assert not re.search(r'\b(syscall|int)\b', disassembly)
        # Compile the XOS layout helper against glibc's selected real TCB
        # definition; this is an object-level contract, not initialized TLS.
        layout = ('#include <tls.h>\n#include <xos_thread_create.h>\n'
                  '_Static_assert(TLS_TCB_AT_TP && !TLS_DTV_AT_TP, "x86 TLS layout");\n'
                  'int probe(const struct xos_thread_reservation *r, unsigned long s, unsigned long a, '
                  'struct xos_thread_tls_layout *l) { return __xos_thread_tls_layout(r, s, a, TLS_TCB_SIZE, l); }\n')
        subprocess.run(cmd, cwd=source / 'csu', check=True, capture_output=True, text=True, input=layout)
        layout_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(obj)], text=True)
        assert '__xos_thread_tls_layout' in layout_code
        glue = ("#include <stddef.h>\n#include <lowlevellock-futex.h>\n"
                "int wait_probe(unsigned *p) { return lll_futex_wait(p, 3, LLL_PRIVATE); }\n"
                "int wake_probe(unsigned *p) { return lll_futex_wake(p, 1, LLL_PRIVATE); }\n"
                "int shared_probe(unsigned *p) { return lll_futex_wait(p, 3, LLL_SHARED); }\n")
        subprocess.run(cmd, cwd=source / 'csu', check=True, capture_output=True, text=True, input=glue)
        glue_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(obj)], text=True)
        assert '__xos_lll_wait' in glue_code and '__xos_lll_wake' in glue_code
        assert re.search(r'\bud2\b', glue_code)
        sysdep = '#include <sysdep.h>\n_Static_assert(SINGLE_THREAD_P == 0, "locks must not be elided");\nvoid probe(void) { INTERNAL_SYSCALL_CALL(exit, 0); }\n'
        subprocess.run(cmd, cwd=source / 'csu', check=True, capture_output=True, text=True, input=sysdep)
        sysdep_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(obj)], text=True)
        assert '__xos_internal_exit' in sysdep_code
        unsupported = '#include <sysdep.h>\nvoid probe(void) { INTERNAL_SYSCALL_CALL(no_such_xos_call, 0); }\n'
        failure = subprocess.run(cmd + ['-Werror=implicit-function-declaration'], cwd=source / 'csu',
                                 capture_output=True, text=True, input=unsupported)
        assert failure.returncode != 0 and '__xos_internal_no_such_xos_call' in failure.stderr
        # Compare the experimental public types to the actual XOS thread ABI.
        cpp = '#include <xos/thread_abi.hpp>\n#define _SEMAPHORE_H 1\n#include <bits/semaphore.h>\n#include <bits/pthread_stack_min-dynamic.h>\n#include <bits/local_lim.h>\nstatic_assert(PTHREAD_STACK_MIN == xos::thread_stack_min);\nstatic_assert(sizeof(sem_t) == 32 && alignof(sem_t) == 8);\nstatic_assert(PTHREAD_KEYS_MAX == 128);\n#define _ERRNO_H 1\n#include <bits/errno.h>\n#include <bits/types/idtype_t.h>\nstatic_assert(EINVAL == 22 && ENOSYS == 88 && EWOULDBLOCK == EAGAIN);\nstatic_assert(P_ALL == 0 && P_PID == 1 && P_PGID == 2);\n'
        cxx = report['tools']['x86_64-elf-g++']['path']
        subprocess.run([cxx, '-std=c++17', '-ffreestanding', '-nostdinc',
                        '-I', str(root / 'src/shared/include'), '-I', str(source / 'sysdeps/xos'),
                        '-x', 'c++', '-c', '-', '-o', str(obj)], input=cpp, text=True,
                       capture_output=True, check=True)
    root = output / 'xos-glibc-sysroot'
    manifest = json.loads((output / 'header-manifest.json').read_text())
    assert digest(output / 'header-manifest.json') == report['header_install']['manifest_sha256']
    assert len(manifest) == report['header_install']['file_count']
    assert set(manifest) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    for name, expected in manifest.items():
        assert digest(root / name) == expected
    assert digest(root / 'usr/include/stdlib.h') == digest(source / 'stdlib/stdlib.h')
    assert digest(root / 'usr/include/bits/stdio_lim.h') == digest(source / 'sysdeps/xos/bits/stdio_lim.h')
    assert digest(root / 'usr/include/bits/semaphore.h') == digest(source / 'sysdeps/xos/bits/semaphore.h')
    assert digest(root / 'usr/include/bits/errno.h') == digest(source / 'sysdeps/xos/bits/errno.h')
    assert digest(root / 'usr/include/bits/mman.h') == digest(source / 'sysdeps/xos/bits/mman.h')
    assert digest(root / 'usr/include/bits/types/idtype_t.h') == digest(source / 'sysdeps/xos/bits/types/idtype_t.h')
    assert digest(output / 'header-client.log') == report['header_client']['log_sha256']
    assert 'gnu/stubs.h' in (output / 'header-client.log').read_text()
    for name in ('pthread_stack_min.h', 'pthread_stack_min-dynamic.h'):
        installed = root / 'usr/include/bits' / name
        assert digest(installed) == digest(source / 'sysdeps/xos/bits' / name)
    bootstrap = report['header_bootstrap_client']
    assert bootstrap['diagnostic_only'] and bootstrap['exit_code'] == 0
    placeholder = output / 'header-bootstrap/gnu/stubs.h'
    assert digest(placeholder) == bootstrap['placeholder_sha256'] == digest(source / 'include/gnu/stubs.h')
    with tarfile.open(args.archive) as archive:
        original = archive.extractfile('glibc-2.44/include/gnu/stubs.h')
        assert original is not None and original.read() == placeholder.read_bytes()
    assert not (root / 'usr/include/gnu/stubs.h').exists()
    assert digest(output / 'header-bootstrap-client.log') == bootstrap['log_sha256']
    assert digest(output / 'header-bootstrap-client.o') == bootstrap['object_sha256']
    depfile = output / 'header-bootstrap-client.d'
    assert digest(depfile) == bootstrap['dependency_file_sha256']
    rule = depfile.read_text().replace('\\\n', ' ').splitlines()[0]
    paths = [Path(x).resolve(strict=True) for x in shlex.split(rule.split(':', 1)[1])]
    assert placeholder.resolve() in paths
    for name in ('pthread_stack_min.h', 'pthread_stack_min-dynamic.h'):
        assert (root / 'usr/include/bits' / name).resolve() in paths
    for path in paths:
        if root.resolve() in path.parents:
            assert str(path.relative_to(root.resolve())) in manifest, path
        else:
            assert path == placeholder.resolve() or compiler_include in path.parents, path
    header_elf = subprocess.check_output(['x86_64-elf-readelf', '-h', str(output / 'header-bootstrap-client.o')], text=True)
    assert 'ELF64' in header_elf and 'Advanced Micro Devices X86-64' in header_elf
    minimum = report['minimum_link']
    assert minimum['exit_code'] == 0
    linked = output / 'minimum-client.elf'
    linkmap = output / 'minimum-client.map'
    assert digest(linked) == minimum['elf_sha256']
    assert digest(linkmap) == minimum['map_sha256']
    assert digest(output / 'minimum-client.log') == minimum['log_sha256']
    assert set(re.findall(r'^LOAD (.+)$', linkmap.read_text(), re.M)) == {
        str(output / 'header-bootstrap-client.o'), str(build / 'stdlib/abs.o'),
        str(build / 'posix/_exit.o'),
    }
    elf = subprocess.check_output([report['readelf'], '-W', '-h', '-l', '-s', str(linked)], text=True)
    assert 'Advanced Micro Devices X86-64' in elf and re.search(r'Type:\s+EXEC\b', elf)
    assert not re.search(r'^\s+(INTERP|DYNAMIC)\s', elf, re.M)
    assert not re.search(r'\bUND[^\S\n]+\S', elf, re.M)
    for name in ('_start', 'abs', '_exit'):
        assert re.search(r'\bFUNC\s+GLOBAL\s+\w+\s+\d+\s+' + name + r'$', elf, re.M)
    for name in ('signal/raise.os', 'signal/sigwait.os', 'stdlib/arc4random.o',
                 'libio/freopen.o', 'libio/freopen64.o', 'dlfcn/dlerror.o'):
        assert digest(build / name) == report['built_objects'][name]
    symbols = subprocess.check_output(['x86_64-elf-readelf', '-Ws', str(build / 'signal/raise.os')], text=True)
    assert re.search(r'GLOBAL\s+HIDDEN\s+\d+\s+__GI_raise\b', symbols)
    assert re.search(r'GLOBAL\s+DEFAULT\s+\d+\s+raise\b', symbols)
    assert re.search(r'WEAK\s+DEFAULT\s+\d+\s+gsignal\b', symbols)
    symbols = subprocess.check_output(['x86_64-elf-readelf', '-Ws', str(build / 'signal/sigwait.os')], text=True)
    assert re.search(r'GLOBAL\s+HIDDEN\s+\d+\s+__GI___sigwait\b', symbols)
    assert re.search(r'WEAK\s+DEFAULT\s+\d+\s+sigwait\b', symbols)
    sigwait_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'signal/sigwait.os')], text=True)
    assert re.search(r'\$0x58,%eax', sigwait_code) and '__libc_errno' not in sigwait_code
    versions = (build / 'soversions.i').read_text()
    assert 'DEFAULT libc 0.1  GLIBC_2.44' in versions
    assert 'DEFAULT libm 0.1  GLIBC_2.44' in versions
    assert '#define MODULE_libc ' in (build / 'libc-modules.h').read_text()
    thread_exit = report['diagnostic_objects']['xos_thread_exit']
    assert thread_exit['exit_code'] == 0 and digest(build / 'nptl/xos_thread_exit.o') == thread_exit['sha256']
    assert '../sysdeps/xos/xos_thread_exit.c' in (output / 'xos_thread_exit-dependencies.d').read_text()
    thread_entry = report['diagnostic_objects']['xos_thread_entry']
    entry_object = build / 'nptl/xos_thread_entry.o'
    assert thread_entry['exit_code'] == 0 and digest(entry_object) == thread_entry['sha256']
    assert 'source/sysdeps/x86_64/xos/xos_thread_entry.S' in dependency_manifest['xos_thread_entry']
    entry_symbols = (output / 'xos_thread_entry-readelf.txt').read_text()
    assert re.search(r'\bFUNC\s+GLOBAL\s+HIDDEN\s+\d+\s+__xos_thread_entry\b', entry_symbols)
    thread_create = report['diagnostic_objects']['xos_thread_create']
    assert thread_create['exit_code'] == 0 and digest(build / 'nptl/xos_thread_create.o') == thread_create['sha256']
    assert '../sysdeps/xos/xos_thread_create.c' in (output / 'xos_thread_create-dependencies.d').read_text()
    create_symbols = subprocess.check_output(['x86_64-elf-readelf', '--wide', '-s', str(build / 'nptl/xos_thread_create.o')], text=True)
    assert all(symbol in create_symbols for symbol in ('__xos_thread_prepare', '__xos_thread_start', '__xos_thread_abort', '__xos_thread_launch', '__xos_thread_tls_layout'))
    thread_tls = report['diagnostic_objects']['xos_thread_tls']
    assert thread_tls['exit_code'] == 0 and digest(build / 'nptl/xos_thread_tls.o') == thread_tls['sha256']
    assert '../sysdeps/xos/xos_thread_tls.c' in (output / 'xos_thread_tls-dependencies.d').read_text()
    tls_symbols = subprocess.check_output(['x86_64-elf-readelf', '--wide', '-s', str(build / 'nptl/xos_thread_tls.o')], text=True)
    assert all(symbol in tls_symbols for symbol in ('__xos_thread_tls_initialize', '__xos_thread_tls_release', '_dl_allocate_tls', '_dl_deallocate_tls'))
    assert '__xos_thread_static_tls_initialize' in tls_symbols and '__xos_dl_init_reserved_tls' in tls_symbols
    dl_tls = report['diagnostic_objects']['dl-tls']
    dl_tls_object = build / 'elf/dl-tls.o'
    assert dl_tls['exit_code'] == 0 and digest(dl_tls_object) == dl_tls['sha256']
    assert 'source/elf/dl-tls.c' in dependency_manifest['dl-tls']
    dl_tls_symbols = subprocess.check_output([report['readelf'], '-Ws', dl_tls_object], text=True)
    assert re.search(r'\bFUNC\s+GLOBAL\s+HIDDEN\s+\d+\s+__xos_dl_init_reserved_tls\b',
                     dl_tls_symbols)
    worker = build / 'nptl/xos_static_worker.o'
    assert digest(worker) == report['diagnostic_objects']['xos_static_worker']['sha256']
    assert 'source/sysdeps/xos/xos_static_worker.c' in dependency_manifest['xos_static_worker']
    code = subprocess.check_output(['x86_64-elf-objdump', '-dr', worker], text=True)
    for symbol in ('__xos_thread_launch', '__xos_thread_static_tls_initialize',
                   '__xos_thread_finish', '__xos_thread_entry'):
        assert re.search(r'R_X86_64_\w+\s+' + symbol + r'\b', code)
    yield_item = report['diagnostic_objects']['sched_yield']
    assert yield_item['exit_code'] == 0 and digest(build / 'posix/sched_yield.o') == yield_item['sha256']
    assert '../sysdeps/xos/sched_yield.c' in (output / 'sched_yield-dependencies.d').read_text()
    yield_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'posix/sched_yield.o')], text=True)
    assert re.search(r'\bmov\s+\$0x3,%eax', yield_code) and re.search(r'\bint\s+\$0x80', yield_code)
    assert not re.search(r'\bsyscall\b', yield_code)
    pid_item = report['diagnostic_objects']['getpid']
    assert pid_item['exit_code'] == 0 and digest(build / 'posix/getpid.o') == pid_item['sha256']
    assert '../sysdeps/xos/getpid.c' in (output / 'getpid-dependencies.d').read_text()
    pid_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'posix/getpid.o')], text=True)
    assert re.search(r'\bmov\s+\$0x6,%eax', pid_code) and re.search(r'\bint\s+\$0x80', pid_code)
    assert not re.search(r'\bsyscall\b', pid_code)
    clock_item = report['diagnostic_objects']['clock_gettime']
    assert clock_item['exit_code'] == 0 and digest(build / 'time/clock_gettime.o') == clock_item['sha256']
    assert '../sysdeps/xos/clock_gettime.c' in (output / 'clock_gettime-dependencies.d').read_text()
    clock_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'time/clock_gettime.o')], text=True)
    assert re.search(r'\bint\s+\$0x80', clock_code) and not re.search(r'\bsyscall\b', clock_code)
    resolution_item = report['diagnostic_objects']['clock_getres']
    assert resolution_item['exit_code'] == 0 and digest(build / 'time/clock_getres.o') == resolution_item['sha256']
    assert '../sysdeps/xos/clock_getres.c' in (output / 'clock_getres-dependencies.d').read_text()
    resolution_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'time/clock_getres.o')], text=True)
    assert re.search(r'\bint\s+\$0x80', resolution_code) and not re.search(r'\bsyscall\b', resolution_code)
    for name in ('getrandom', 'getentropy'):
        item = report['diagnostic_objects'][name]
        assert item['exit_code'] == 0 and digest(build / 'stdlib' / (name + '.o')) == item['sha256']
        assert '../sysdeps/xos/' + name + '.c' in (output / (name + '-dependencies.d')).read_text()
    random_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'stdlib/getrandom.o')], text=True)
    assert re.search(r'\bmov\s+\$0x3f,%eax', random_code) and re.search(r'\bint\s+\$0x80', random_code)
    assert not re.search(r'\bsyscall\b', random_code)
    sigset = report['diagnostic_objects']['sigset']
    assert sigset['exit_code'] == 0 and digest(build / 'signal/sigset.o') == sigset['sha256']
    sigset_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'signal/sigset.o')], text=True)
    assert '$0x58' in sigset_code and '$0xffffffffffffffff' in sigset_code
    cancellation = report['diagnostic_objects']['cancellation']
    assert cancellation['exit_code'] == 0 and digest(build / 'nptl/cancellation.o') == cancellation['sha256']
    assert '../sysdeps/xos/cancellation.c' in (output / 'cancellation-dependencies.d').read_text()
    cancel_symbols = subprocess.check_output(['x86_64-elf-readelf', '-Ws', str(build / 'nptl/cancellation.o')], text=True)
    for name in ('__internal_syscall_cancel', '__syscall_cancel', '__syscall_do_cancel'):
        assert re.search(r'GLOBAL\s+HIDDEN\s+\d+\s+' + name + r'\b', cancel_symbols)
    cancel_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'nptl/cancellation.o')], text=True)
    assert '$0xffffffffffffffa8,%rax' in cancel_code and '$0x58' in cancel_code
    assert re.search(r'\bud2\b', cancel_code) and not re.search(r'\b(syscall|int)\b', cancel_code)
    native_wait = report['diagnostic_objects']['xos_wait_word']
    assert native_wait['exit_code'] == 0 and digest(build / 'nptl/xos_wait_word.o') == native_wait['sha256']
    assert '../sysdeps/xos/xos_wait_word.c' in (output / 'xos_wait_word-dependencies.d').read_text()
    wait_symbols = (output / 'xos_wait_word-readelf.txt').read_text()
    assert '__xos_wait_word' in wait_symbols and '__xos_wake_word' in wait_symbols
    adapter = report['diagnostic_objects']['xos_lll_futex']
    assert adapter['exit_code'] == 0 and digest(build / 'nptl/xos_lll_futex.o') == adapter['sha256']
    assert '../sysdeps/xos/xos_lll_futex.c' in (output / 'xos_lll_futex-dependencies.d').read_text()
    fd_path = report['diagnostic_objects']['fd_to_filename']
    assert fd_path['exit_code'] == 0 and digest(build / 'misc/fd_to_filename.o') == fd_path['sha256']
    assert '../sysdeps/xos/fd_to_filename.c' in (output / 'fd_to_filename-dependencies.d').read_text()
    for name in ('freopen.o', 'freopen64.o'):
        code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'libio' / name)], text=True)
        assert '__fd_to_filename' in code and '_IO_file_close_maybe_unlink' in code
    for name in ('xos_timed_wait', 'futex-internal'):
        item = report['diagnostic_objects'][name]
        assert item['exit_code'] == 0 and digest(build / ('nptl/' + name + '.o')) == item['sha256']
        assert '../sysdeps/xos/' + name + '.c' in (output / (name + '-dependencies.d')).read_text()
    timed_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'nptl/futex-internal.o')], text=True)
    assert '__xos_wait_monotonic' in timed_code and re.search(r'\bud2\b', timed_code)
    assert not re.search(r'\b(syscall|int)\b', timed_code)
    xid = report['diagnostic_objects']['nptl_setxid']
    assert xid['exit_code'] == 0 and digest(build / 'nptl/nptl_setxid.o') == xid['sha256']
    assert '../sysdeps/xos/nptl_setxid.c' in (output / 'nptl_setxid-dependencies.d').read_text()
    xid_obj = build / 'nptl/nptl_setxid.o'
    xid_symbols = subprocess.check_output(['x86_64-elf-readelf', '-Ws', str(xid_obj)], text=True)
    for name in ('__nptl_setxid', '__nptl_setxid_sighandler'):
        assert re.search(r'GLOBAL\s+HIDDEN\s+\d+\s+' + name + r'\b', xid_symbols)
    xid_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(xid_obj)], text=True)
    assert '$0x58' in xid_code and re.search(r'\bud2\b', xid_code)
    assert not re.search(r'\b(syscall|int)\b', xid_code)
    sem_init = report['diagnostic_objects']['sem_init']
    assert sem_init['exit_code'] == 0 and digest(build / 'nptl/sem_init.o') == sem_init['sha256']
    assert 'sem_init.c' in (output / 'sem_init-dependencies.d').read_text()
    sem_post = report['diagnostic_objects']['sem_post']
    assert sem_post['exit_code'] == 0 and digest(build / 'nptl/sem_post.o') == sem_post['sha256']
    assert 'sem_post.c' in (output / 'sem_post-dependencies.d').read_text()
    sem_post_symbols = subprocess.check_output(['x86_64-elf-readelf', '--wide', '-s', str(build / 'nptl/sem_post.o')], text=True)
    assert '__xos_lll_wake' in sem_post_symbols and '__libc_fatal' in sem_post_symbols
    pthread_cancel = report['diagnostic_objects']['pthread_cancel']
    assert pthread_cancel['exit_code'] == 0 and digest(build / 'nptl/pthread_cancel.o') == pthread_cancel['sha256']
    assert '../sysdeps/xos/pthread_cancel.c' in (output / 'pthread_cancel-dependencies.d').read_text()
    cancel_code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'nptl/pthread_cancel.o')], text=True)
    assert '$0x86,%eax' in cancel_code and '__libc_errno' not in cancel_code
    assert not re.search(r'\b(syscall|int)\b', cancel_code)
    secure = report['diagnostic_objects']['check_fds']
    assert secure['exit_code'] == 0 and digest(build / 'csu/check_fds.o') == secure['sha256']
    assert '../sysdeps/xos/check_fds.c' in (output / 'check_fds-dependencies.d').read_text()
    disassembly = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(build / 'csu/check_fds.o')], text=True)
    assert re.search(r'\bmov\s+\$0x7f,%edi', disassembly) and re.search(r'R_X86_64_\w+\s+_exit', disassembly)

    for subdir, name, trap, symbol in (
        ('misc', 'brk', '1d', '__brk'),
        ('elf', 'dl-early_allocate', '1d', '_dl_early_allocate'),
        ('misc', 'mmap', '43', '__mmap'),
        ('misc', 'mmap64', None, '__mmap64'),
        ('misc', 'mprotect', '43', '__mprotect'),
        ('misc', 'munmap', '43', '__munmap'),
    ):
        obj = build / subdir / (name + '.o')
        item = report['diagnostic_objects'][name]
        assert item['exit_code'] == 0 and digest(obj) == item['sha256'], name
        assert f'source/sysdeps/xos/{name}.c' in dependency_manifest[name]
        symbols = subprocess.check_output([report['readelf'], '-Ws', obj], text=True)
        assert re.search(r'\bFUNC\b.*\s\d+\s+' + symbol + r'\s*$', symbols, re.M)
        code = subprocess.check_output(['x86_64-elf-objdump', '-dr', obj], text=True)
        if trap is None:
            assert re.search(r'R_X86_64_\w+\s+__mmap\b', code)
        else:
            assert re.search(r'\$0x' + trap + r',%(e|r)ax\b', code)
            assert re.search(r'\bint\s+\$0x80\b', code) and '\tsyscall' not in code
        if name == 'dl-early_allocate':
            assert 'errno' not in code and not re.search(r'%fs:', code)

    print('PASS diagnostic objects, symbols, instruction sequence, header provenance and partial sysroot')
    print('NOT ACCEPTED: experimental backend, incomplete headers and libc build, no guest test')


if __name__ == '__main__':
    main()
