#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce an isolated glibc XOS configuration investigation (not a build)."""
import argparse
import hashlib
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import sys
import tarfile

from glibc_g1_deps import collect_dependency_files

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_identity(name):
    executable = shutil.which(name)
    if not executable:
        return {'available': False}
    executable = Path(executable).resolve(strict=True)
    version = subprocess.run([str(executable), '--version'], capture_output=True, text=True)
    return {'available': True, 'path': str(executable), 'sha256': digest(executable),
            'version_exit_code': version.returncode,
            'version': (version.stdout or version.stderr).splitlines()[0] if (version.stdout or version.stderr) else ''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new private research directory')
    parser.add_argument('--xos-backend', action='store_true', help='select the experimental XOS sysdeps without pretending the port is complete')
    parser.add_argument('--hacker-mode', action='store_true', help='diagnostic only: bypass upstream unsupported-platform guard')
    parser.add_argument('--diagnose-nptl', action='store_true', help='diagnostic only: use an empty XOS marker and synthetic ABI tag to expose NPTL dependencies')
    parser.add_argument('--synthetic-abi-tag', action='store_true', help='diagnostic only: add a deliberately fake ABI tag to expose later build failures')
    args = parser.parse_args()
    backend = args.xos_backend or args.diagnose_nptl
    if args.synthetic_abi_tag and not backend:
        parser.error('--synthetic-abi-tag requires --xos-backend or --diagnose-nptl')
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
    if backend:
        marker = source / 'sysdeps/xos'
        marker.mkdir()
        overlay = ROOT / 'src/ports/glibc/sysdeps'
        for path in sorted(overlay.rglob('*')):
            if path.is_file():
                destination = source / 'sysdeps' / path.relative_to(overlay)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        note_patch = ROOT / 'src/ports/glibc/patches/0002-xos-abi-note.patch'
        subprocess.run(['patch', '-p1', '-i', str(note_patch)], cwd=source, check=True)
        tls_patch = ROOT / 'src/ports/glibc/patches/0003-xos-tls-init.patch'
        subprocess.run(['patch', '-p1', '-i', str(tls_patch)], cwd=source, check=True)
        sigset_patch = ROOT / 'src/ports/glibc/patches/0004-sigset-error-pointer.patch'
        subprocess.run(['patch', '-p1', '-i', str(sigset_patch)], cwd=source, check=True)
        raise_patch = ROOT / 'src/ports/glibc/patches/0005-raise-hidden-alias.patch'
        subprocess.run(['patch', '-p1', '-i', str(raise_patch)], cwd=source, check=True)
        sigwait_patch = ROOT / 'src/ports/glibc/patches/0006-sigwait-failure.patch'
        subprocess.run(['patch', '-p1', '-i', str(sigwait_patch)], cwd=source, check=True)
        atomic_patch = ROOT / 'src/ports/glibc/patches/0007-arc4random-atomic-include.patch'
        subprocess.run(['patch', '-p1', '-i', str(atomic_patch)], cwd=source, check=True)
        freopen_patch = ROOT / 'src/ports/glibc/patches/0008-freopen-no-fd-path.patch'
        subprocess.run(['patch', '-p1', '-i', str(freopen_patch)], cwd=source, check=True)
        dlerror_patch = ROOT / 'src/ports/glibc/patches/0009-dlerror-errno-include.patch'
        subprocess.run(['patch', '-p1', '-i', str(dlerror_patch)], cwd=source, check=True)
        sem_init_patch = ROOT / 'src/ports/glibc/patches/0010-sem-init-private-only.patch'
        subprocess.run(['patch', '-p1', '-i', str(sem_init_patch)], cwd=source, check=True)
        nptl_include_patch = ROOT / 'src/ports/glibc/patches/0011-nptl-explicit-includes.patch'
        subprocess.run(['patch', '-p1', '-i', str(nptl_include_patch)], cwd=source, check=True)
        socket_types_patch = ROOT / 'src/ports/glibc/patches/0012-socket-include-types.patch'
        subprocess.run(['patch', '-p1', '-i', str(socket_types_patch)], cwd=source, check=True)
        # This value is deliberately synthetic and is never an XOS ABI assignment.
        if args.synthetic_abi_tag:
            with (source / 'abi-tags').open('a') as file:
                file.write('\n.*-.*-xos.* 255 0.0.0\n')
    target = subprocess.check_output([source/'scripts/config.sub', 'x86_64-unknown-xos'], text=True).strip()
    build = output / 'configure'
    build.mkdir()
    command = [str(source/'configure'), '--build=aarch64-apple-darwin', '--host=x86_64-unknown-xos', '--prefix=/usr', '--disable-werror']
    if args.hacker_mode:
        command.append('--enable-hacker-mode')
    env = os.environ.copy()
    env['CC'] = 'x86_64-elf-gcc'
    env['CXX'] = 'x86_64-elf-g++'
    compiler_path = Path(shutil.which(env['CC'])).resolve(strict=True)
    compiler_target = subprocess.check_output([env['CC'], '-dumpmachine'], text=True).strip()
    sysroot = output / 'xos-glibc-sysroot'
    sysroot.mkdir()
    if backend:
        # Force an empty, private sysroot; retain GCC's own freestanding headers.
        for name, compiler in (('cc', env['CC']), ('cxx', env['CXX'])):
            wrapper = output / name
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(shutil.which(compiler))
                               + ' --sysroot=' + shlex.quote(str(sysroot)) + ' "$@"\n')
            wrapper.chmod(0o755)
        env['CC'], env['CXX'] = str(output / 'cc'), str(output / 'cxx')
    with (output/'configure.log').open('w') as log:
        result = subprocess.run(command, cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
    make_result = None
    if backend and result.returncode == 0:
        with (output/'make.log').open('w') as log:
            make_result = subprocess.run(['gnumake', '-j1'], cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
    objects = {}
    if backend and make_result is not None:
        for subdir, name in (('stdlib', 'abs'), ('posix', '_exit'), ('csu', 'abi-note'), ('csu', 'check_fds'), ('nptl', 'xos_wait_word'), ('nptl', 'xos_lll_futex'), ('nptl', 'xos_thread_exit'), ('nptl', 'xos_thread_create'), ('nptl', 'xos_thread_tls'), ('signal', 'sigset'), ('misc', 'fd_to_filename'), ('nptl', 'cancellation'), ('nptl', 'xos_timed_wait'), ('nptl', 'futex-internal'), ('nptl', 'nptl_setxid'), ('nptl', 'pthread_cancel'), ('nptl', 'sem_init'), ('nptl', 'sem_post'), ('posix', 'sched_yield'), ('posix', 'getpid'), ('time', 'clock_gettime'), ('time', 'clock_getres')):
            (build / subdir).mkdir(exist_ok=True)
            target_object = build / subdir / (name + '.o')
            with (output / (name + '-object.log')).open('w') as log:
                obj_result = subprocess.run(['gnumake', '-C', str(source / subdir),
                    'objdir=' + str(build), str(target_object)], env=env,
                    stdout=log, stderr=subprocess.STDOUT)
            item = {'exit_code': obj_result.returncode,
                    'log_sha256': digest(output / (name + '-object.log'))}
            if obj_result.returncode == 0 and target_object.is_file():
                readelf = subprocess.run(['x86_64-elf-readelf', '-h', '-s', str(target_object)],
                                         capture_output=True, text=True, check=True)
                (output / (name + '-readelf.txt')).write_text(readelf.stdout)
                item.update({'sha256': digest(target_object),
                             'readelf_sha256': digest(output / (name + '-readelf.txt'))})
                for suffix in ('.d', '.dt'):
                    dep = Path(str(target_object) + suffix)
                    if dep.is_file():
                        saved_dep = output / (name + '-dependencies.d')
                        shutil.copyfile(dep, saved_dep)
                        item['dependency_file_sha256'] = digest(saved_dep)
                        break
            objects[name] = item
    # This separate probe suppresses the blocked csu before-compile prerequisites
    # only to inspect sysdeps source selection and note contents. It is not a
    # successful normal csu build, whose failure is retained above.
    isolated_note = None
    if backend and make_result is not None and objects['abi-note']['exit_code'] != 0:
        note_object = build / 'csu/abi-note.o'
        with (output / 'abi-note-isolated.log').open('w') as log:
            isolated = subprocess.run(['gnumake', '-C', str(source / 'csu'),
                'objdir=' + str(build), 'before-compile=', str(note_object)],
                env=env, stdout=log, stderr=subprocess.STDOUT)
        isolated_note = {'exit_code': isolated.returncode, 'suppresses_before_compile': True,
                         'log_sha256': digest(output / 'abi-note-isolated.log')}
        if isolated.returncode == 0 and note_object.is_file():
            notes = subprocess.check_output(['x86_64-elf-readelf', '-n', str(note_object)], text=True)
            (output / 'abi-note-readelf.txt').write_text(notes)
            isolated_note.update({'object_sha256': digest(note_object),
                                  'notes_sha256': digest(output / 'abi-note-readelf.txt')})
    if backend and objects.get('abi-note', {}).get('exit_code') == 0:
        note_object = build / 'csu/abi-note.o'
        notes = subprocess.check_output(['x86_64-elf-readelf', '-n', str(note_object)], text=True)
        (output / 'abi-note-readelf.txt').write_text(notes)
        objects['abi-note']['notes_sha256'] = digest(output / 'abi-note-readelf.txt')
    layout_headers = {name: digest(build / name) for name in
                      ('sem_t-align.h', 'tcb-offsets.h', 'tlsdesc.h') if (build / name).is_file()}
    header_install = None
    if backend and make_result is not None:
        with (output / 'install-headers.log').open('w') as log:
            install = subprocess.run(['gnumake', '-C', str(build), 'install-headers',
                                      'DESTDIR=' + str(sysroot)], env=env,
                                     stdout=log, stderr=subprocess.STDOUT)
        headers = {str(p.relative_to(sysroot)): digest(p) for p in sorted(sysroot.rglob('*')) if p.is_file()}
        (output / 'header-manifest.json').write_text(json.dumps(headers, indent=2) + '\n')
        header_install = {'exit_code': install.returncode, 'file_count': len(headers),
                          'log_sha256': digest(output / 'install-headers.log'),
                          'manifest_sha256': digest(output / 'header-manifest.json')}
    header_client = None
    if backend and header_install is not None:
        client_source = ('#include <errno.h>\n#include <stdio.h>\n#include <pthread.h>\n'
                         '#include <semaphore.h>\n#include <sys/wait.h>\n#include <limits.h>\n'
                         '_Static_assert(PTHREAD_STACK_MIN == 65536, "stack");\n'
                         '_Static_assert(sizeof(sem_t) == 32, "sem");\n'
                         '_Static_assert(EINVAL == 22 && SEM_VALUE_MAX == 2147483647, "limits");\n'
                         'int probe(void) { return EINVAL; }\n')
        with (output / 'header-client.log').open('w') as log:
            client = subprocess.run([env['CC'], '-isystem', str(sysroot / 'usr/include'),
                                     '-ffreestanding', '-x', 'c', '-c', '-',
                                     '-o', str(output / 'header-client.o')],
                                    input=client_source, text=True, stdout=log, stderr=subprocess.STDOUT)
        header_client = {'exit_code': client.returncode,
                         'log_sha256': digest(output / 'header-client.log')}
        if client.returncode == 0:
            header_client['object_sha256'] = digest(output / 'header-client.o')
    # The upstream build-only placeholder is kept outside the sysroot.  It
    # exposes further installed-header errors without pretending to provide a
    # complete, distributable gnu/stubs.h or a successful ordinary client.
    bootstrap_client = None
    if backend and header_client is not None:
        bootstrap = output / 'header-bootstrap'
        (bootstrap / 'gnu').mkdir(parents=True)
        shutil.copyfile(source / 'include/gnu/stubs.h', bootstrap / 'gnu/stubs.h')
        depfile = output / 'header-bootstrap-client.d'
        obj = output / 'header-bootstrap-client.o'
        with (output / 'header-bootstrap-client.log').open('w') as log:
            client = subprocess.run([env['CC'], '-isystem', str(bootstrap),
                                     '-isystem', str(sysroot / 'usr/include'),
                                     '-ffreestanding', '-MD', '-MF', str(depfile),
                                     '-MT', str(obj), '-x', 'c', '-c', '-', '-o', str(obj)],
                                    input=client_source, text=True, stdout=log, stderr=subprocess.STDOUT)
        bootstrap_client = {'exit_code': client.returncode, 'diagnostic_only': True,
                            'placeholder_sha256': digest(bootstrap / 'gnu/stubs.h'),
                            'log_sha256': digest(output / 'header-bootstrap-client.log')}
        if client.returncode == 0:
            bootstrap_client['object_sha256'] = digest(obj)
            bootstrap_client['dependency_file_sha256'] = digest(depfile)
    # Bind every successfully compiled diagnostic object's actual inputs,
    # including generated build headers, and reject headers outside the
    # extracted source, private build tree and compiler freestanding headers.
    compiler_include = Path(subprocess.check_output(
        [str(compiler_path), '-print-file-name=include'], text=True).strip())
    dependency_manifest = {}
    for name, item in objects.items():
        if item['exit_code'] == 0:
            depfile = output / (name + '-dependencies.d')
            if not depfile.is_file():
                raise RuntimeError('missing dependency file for ' + name)
            dependency_manifest[name] = collect_dependency_files(
                depfile, source, build, compiler_include, name)
    if dependency_manifest:
        (output / 'dependency-manifest.json').write_text(
            json.dumps(dependency_manifest, sort_keys=True, indent=2) + '\n')
    built_objects = {}
    if backend and make_result is not None:
        for name in ('signal/raise.os', 'signal/sigwait.os', 'stdlib/arc4random.o', 'libio/freopen.o', 'libio/freopen64.o', 'dlfcn/dlerror.o'):
            obj = build / name
            if obj.is_file():
                built_objects[name] = digest(obj)
    tool_names = ('x86_64-elf-gcc', 'x86_64-elf-g++', 'x86_64-elf-as',
                  'x86_64-elf-ld', 'x86_64-elf-readelf', 'x86_64-elf-objdump',
                  'gnumake', 'gawk', 'bison', 'patch')
    tools = {name: tool_identity(name) for name in tool_names}
    report = {'status': 'diagnostic_only', 'probe_sha256': digest(Path(__file__)), 'tools': tools, 'source_sha256': digest(archive),
              'source_authentication': lock['signature_verification'], 'patch_sha256': digest(patch),
              'canonical_target': target, 'command': command, 'cc': env['CC'],
              'cxx': env['CXX'], 'compiler_target': compiler_target,
              'compiler_path': str(compiler_path), 'compiler_sha256': digest(compiler_path),
              'hacker_mode': args.hacker_mode, 'configure_exit_code': result.returncode,
              'nptl_backend_experimental': backend,
              'synthetic_abi_tag': args.synthetic_abi_tag,
              'private_sysroot_initially_empty': str(sysroot),
              'sysroot_enforced': backend, 'diagnostic_objects': objects,
              'header_install': header_install, 'header_client': header_client, 'header_bootstrap_client': bootstrap_client, 'isolated_abi_note': isolated_note,
              'built_objects': built_objects,
              'generated_layout_headers': layout_headers,
              'dependency_manifest_sha256': digest(output / 'dependency-manifest.json') if dependency_manifest else None,
              'dependency_collector_sha256': digest(ROOT / 'scripts/glibc_g1_deps.py'),
              'xos_abi_note_patch_sha256': digest(note_patch) if backend else None,
              'xos_tls_patch_sha256': digest(tls_patch) if backend else None,
              'sigset_patch_sha256': digest(sigset_patch) if backend else None,
              'raise_patch_sha256': digest(raise_patch) if backend else None,
              'sigwait_patch_sha256': digest(sigwait_patch) if backend else None,
              'atomic_patch_sha256': digest(atomic_patch) if backend else None,
              'freopen_patch_sha256': digest(freopen_patch) if backend else None,
              'dlerror_patch_sha256': digest(dlerror_patch) if backend else None,
              'sem_init_patch_sha256': digest(sem_init_patch) if backend else None,
              'nptl_include_patch_sha256': digest(nptl_include_patch) if backend else None,
              'socket_types_patch_sha256': digest(socket_types_patch) if backend else None,
              'xos_overlay_sha256': {str(p.relative_to(ROOT / 'src/ports/glibc/sysdeps')): digest(p) for p in (ROOT / 'src/ports/glibc/sysdeps').rglob('*') if p.is_file()},
              'configure_log_sha256': digest(output/'configure.log'),
              'not_claimed': ['complete XOS sysdeps', 'target runtime', 'guest qualification', 'distributable source']}
    if make_result is not None:
        report['make_exit_code'] = make_result.returncode
        report['make_log_sha256'] = digest(output/'make.log')
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    # An exploratory incomplete backend cannot count as a successful full build.
    if backend:
        return result.returncode or (make_result.returncode if make_result is not None else 1) or 1
    return result.returncode

if __name__ == '__main__':
    sys.exit(main())
