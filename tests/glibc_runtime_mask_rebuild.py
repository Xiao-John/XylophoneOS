#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recompile the unsigned CLOEXEC fix and relink GNU libc without changing its producer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from archive_member_map import read_archive
from glibc_g1_probe import clean_build_environment


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-build', 'source', 'installed-libc', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    runtime, source, installed = (p.resolve(strict=True) for p in
                                  (args.runtime_build, args.source, args.installed_libc))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'actual GNU compile, archive substitution and shared-library relink',
              'changes': 'two explicit unsigned O_CLOEXEC masks', 'commands': [], 'inputs': {}}
    inputs = report['inputs']
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    report['sanitized_environment'] = removed

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError('input digest mismatch: ' + str(path))
        if str(path) in inputs and inputs[str(path)] != actual:
            raise ValueError('input changed: ' + str(path))
        inputs[str(path)] = actual
        return actual

    def run(name, argv, cwd):
        command = list(map(str, argv))
        report['commands'].append({'name': name, 'argv': command, 'cwd': str(cwd)})
        bind(command[0])
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(command, cwd=cwd, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)

    def dependencies(path, cwd):
        text = Path(path).read_text().replace('\\\n', ' ').splitlines()[0]
        return {str((cwd / item).resolve(strict=True)) for item in shlex.split(text.split(':', 1)[1])}

    try:
        bind(__file__)
        bind(ROOT / 'scripts/archive_member_map.py')
        bind(ROOT / 'scripts/glibc_g1_probe.py')
        bind(runtime / 'manifest.json')
        metadata = json.loads((runtime / 'manifest.json').read_bytes())
        if metadata.get('status') != 'public_runtime_built_not_run' or not metadata.get('public_startup'):
            raise ValueError('a completed public GNU producer is required')
        for name, expected in metadata['artifacts'].items():
            bind(runtime / name, expected)
        upstream = runtime / metadata['source']
        original_source = upstream / 'sysdeps/xos/xos_file_runtime.c'
        original_digest = metadata['port_inputs']['src/ports/glibc/sysdeps/xos/xos_file_runtime.c']
        bind(original_source, original_digest)
        before, after = original_source.read_bytes(), source.read_bytes()
        old, new = b'object->flags & ~O_CLOEXEC, 0', b'object->flags & ~(unsigned int) O_CLOEXEC, 0'
        if before.count(old) != 2 or before.replace(old, new) != after:
            raise ValueError('source delta must be exactly the two explicit unsigned masks')
        bind(source)
        copied = out / 'source/xos_file_runtime.c'
        copied.parent.mkdir()
        copied.write_bytes(after)
        bind(copied, sha(source))
        report['source_before_sha256'] = original_digest
        report['source_after_sha256'] = sha(source)
        build_log = runtime / 'build-public-runtime.log'
        bind(build_log)
        lines = build_log.read_text().replace('\\\n', ' ').splitlines()
        old_object = runtime / 'gnu/io/xos_file_runtime.os'
        new_object = out / 'xos_file_runtime.os'
        cwd = upstream / 'io'
        compile_lines = [line for line in lines if '../sysdeps/xos/xos_file_runtime.c -c ' in line
                         and ' -o ' + str(old_object) + ' ' in line]
        if len(compile_lines) != 1:
            raise ValueError('the exact original shared-object compile command is required')
        original_dependencies = dependencies(old_object.with_suffix('.os.dt'), cwd)
        for path in original_dependencies:
            bind(path)
        replacements = {'../sysdeps/xos/xos_file_runtime.c': str(copied),
                        str(old_object): str(new_object), str(old_object) + '.dt': str(new_object) + '.dt'}
        command = [replacements.get(arg, arg) for arg in shlex.split(compile_lines[0])]
        run('compile_corrected_shared_object', command, cwd)
        current_dependencies = dependencies(str(new_object) + '.dt', cwd)
        if current_dependencies != (original_dependencies - {str(original_source)}) | {str(copied)}:
            raise ValueError('recompiled include closure differs from the original shared object')
        objcopy, ar = shutil.which('x86_64-elf-objcopy'), shutil.which('x86_64-elf-ar')
        if not objcopy or not ar:
            raise ValueError('matching GNU target binutils are required')
        for name, path in (('objcopy', objcopy), ('ar', ar)):
            candidates = [entry for entry in metadata['tools'].values() if isinstance(entry, dict)
                          and entry.get('sha256') == sha(path)]
            if not candidates:
                raise ValueError(name + ' is not from the original producer toolchain')
        for label, path in (('old', old_object), ('new', new_object)):
            run('strip_object_' + label, [objcopy, '--strip-debug', path, out / (label + '_object.os')], out)
        if (out / 'old_object.os').read_bytes() != (out / 'new_object.os').read_bytes():
            raise ValueError('corrected non-debug object differs; full runtime rebuild is required')
        report['non_debug_object_sha256'] = sha(out / 'new_object.os')
        archive = runtime / 'gnu/libc_pic.a'
        bind(archive)
        before_members = read_archive(archive)
        if before_members.get('xos_file_runtime.os') != old_object.read_bytes():
            raise ValueError('original shared object is not the actual linked GNU archive member')
        copied_archive = out / 'libc_pic.a'
        shutil.copyfile(archive, copied_archive)
        run('replace_archive_member', [ar, 'rD', copied_archive, new_object], out)
        after_members = read_archive(copied_archive)
        if list(before_members) != list(after_members):
            raise ValueError('archive member identity/order changed')
        for name, data in before_members.items():
            expected = new_object.read_bytes() if name == 'xos_file_runtime.os' else data
            if after_members[name] != expected:
                raise ValueError('unexpected changed GNU archive member: ' + name)
        report['archive_members'] = len(after_members)
        report['unchanged_archive_members'] = len(after_members) - 1
        partial_lines = [line for line in lines if ' -nostdlib -nostartfiles -r -o ' in line
                         and 'libc_pic.os ' in line and '--whole-archive' in line]
        link_lines = [line for line in lines if ' -shared -static-libgcc ' in line
                      and ' -o ' + str(runtime / 'gnu/libc.so') + ' ' in line]
        if len(partial_lines) != 1 or len(link_lines) != 1:
            raise ValueError('original GNU partial/final link commands are not unique')
        partial = out / 'libc_pic.os'
        rewrite = {str(archive): str(copied_archive), str(runtime / 'gnu/libc_pic.os'): str(partial)}
        run('partial_link', [rewrite.get(arg, arg) for arg in shlex.split(partial_lines[0])], upstream)
        options = runtime / 'gnu/libc_pic.opts'
        bind(options)
        cleaned = out / 'libc_pic.os.clean'
        run('clean_stubs', [objcopy, '@' + str(options), partial, cleaned], upstream)
        library = out / 'libc.so'
        rewrite = {str(runtime / 'gnu/libc_pic.os.clean'): str(cleaned),
                   str(runtime / 'gnu/libc.so'): str(library)}
        run('link_corrected_libc', [rewrite.get(arg, arg) for arg in shlex.split(link_lines[0])], upstream)
        result = out / 'libc.so.0.1'
        run('strip_corrected_libc', [objcopy, '--strip-debug', library, result], out)
        bind(installed)
        if result.read_bytes() != installed.read_bytes():
            raise ValueError('final installed libc bytes differ; restage and rerun the guest')
        report['installed_libc_sha256'] = sha(result)
        report['artifacts'] = {name: sha(out / name) for name in
                               ('xos_file_runtime.os', 'new_object.os', 'libc_pic.a', 'libc.so', 'libc.so.0.1')}
        for path, expected in inputs.items():
            if sha(path) != expected:
                raise ValueError('bound input changed during rebuild: ' + path)
        report['status'] = 'rebuilt_installed_bytes_identical'
        print('PASS actual GNU source recompile and complete libc relink; installed bytes identical', flush=True)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
