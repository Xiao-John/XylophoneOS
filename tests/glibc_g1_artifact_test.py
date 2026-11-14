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
                          ('0009-dlerror-errno-include.patch', 'dlerror_patch_sha256')):
        assert digest(root / 'src/ports/glibc/patches' / filename) == report[key]
    assert report['status'] == 'diagnostic_only' and report['nptl_backend_experimental'] and not report['synthetic_abi_tag']
    assert report['sysroot_enforced'] and report['configure_exit_code'] == 0
    assert not report['hacker_mode'] and '--enable-hacker-mode' not in report['command']
    assert report['make_exit_code'] != 0 and report['header_install']['exit_code'] == 0
    assert report['header_client']['exit_code'] != 0
    source = output / 'glibc-2.44'
    build = output / 'configure'
    with tarfile.open(args.archive) as tar:
        original = tar.extractfile('glibc-2.44/stdlib/abs.c')
        assert original is not None and original.read() == (source / 'stdlib/abs.c').read_bytes()
    sysdirs = (build / 'config.make').read_text()
    assert 'sysdeps/xos' in sysdirs and 'sysdeps/x86_64/xos' in sysdirs
    assert 'experimental and incomplete' in (output / 'configure.log').read_text()
    assert not re.search(r'^\.\*-\.\*-xos', (source / 'abi-tags').read_text(), re.M)
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
    assert digest(root / 'usr/include/bits/types/idtype_t.h') == digest(source / 'sysdeps/xos/bits/types/idtype_t.h')
    assert digest(output / 'header-client.log') == report['header_client']['log_sha256']
    assert 'gnu/stubs.h' in (output / 'header-client.log').read_text()
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
    thread_create = report['diagnostic_objects']['xos_thread_create']
    assert thread_create['exit_code'] == 0 and digest(build / 'nptl/xos_thread_create.o') == thread_create['sha256']
    assert '../sysdeps/xos/xos_thread_create.c' in (output / 'xos_thread_create-dependencies.d').read_text()
    create_symbols = (output / 'xos_thread_create-readelf.txt').read_text()
    assert all(symbol in create_symbols for symbol in ('__xos_thread_prepare', '__xos_thread_start', '__xos_thread_abort'))
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

    print('PASS diagnostic objects, symbols, instruction sequence, header provenance and partial sysroot')
    print('NOT ACCEPTED: experimental backend, incomplete headers and libc build, no guest test')


if __name__ == '__main__':
    main()
