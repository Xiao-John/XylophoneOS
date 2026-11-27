# SPDX-License-Identifier: Apache-2.0
"""Recompile three shared libc objects using a bound, already configured GNU build."""

import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

from archive_member_map import read_archive
from xypm_format import canonical, require, sha_file

ROOT = Path(__file__).resolve().parents[3]
PORT = ROOT / 'src/ports/glibc'
NAMES = ('dlopen', 'dlmopen', 'dlclose')
MACRO = '-DXOS_DLFUNC_FIXED_CLOSURE'


def recorded_command(log, compiler, predicate):
    command, = (shlex.split(line) for line in log.replace('\\\n', ' ').splitlines()
                if line.startswith(str(compiler) + ' ') and predicate(line))
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shared-build', type=Path, required=True)
    parser.add_argument('--pic-log-sha256', required=True)
    parser.add_argument('--link-log-sha256', required=True)
    parser.add_argument('--libc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    shared = args.shared_build.resolve(strict=True)
    prepared = shared / 'prepared'
    source = prepared / 'glibc-2.44'
    compiler = prepared / 'cc'
    build = shared / 'gnu'
    pic_log = shared / 'pic.log'
    link_log = shared / 'libc-link.log'
    require(sha_file(pic_log) == args.pic_log_sha256 and sha_file(link_log) == args.link_log_sha256
            and sha_file(build / 'libc.so') == args.libc_sha256, 'existing GNU build or command logs differ')
    pics = pic_log.read_text()
    commands = {
        'prelink': recorded_command(pics, compiler, lambda line: ' -r -o ' in line and 'libc_pic.os' in line),
        'link': recorded_command(link_log.read_text(), compiler,
                                 lambda line: ' -o ' + str(build / 'libc.so') + ' ' in line),
    }
    inputs = {name: sha_file(build / 'dlfcn' / (name + '.os')) for name in NAMES}
    options = build / 'libc_pic.opts'
    original = build / 'libc_pic.a'
    args.output.mkdir(parents=True)
    with TemporaryDirectory() as folder:
        work = Path(folder)
        copied = work / 'dlfcn'
        copied.mkdir()
        for name in NAMES:
            shutil.copyfile(source / 'dlfcn' / (name + '.c'), copied / (name + '.c'))
        patch = PORT / 'patches/0038-xos-public-dlfcn-fixed-closure.patch'
        subprocess.run(['patch', '-p1', '-i', patch], cwd=work, check=True)
        members = []
        for name in NAMES:
            require('CFLAGS-' + name + '.os += ' + MACRO in (PORT / 'sysdeps/xos/Makefile').read_text(),
                    'the shared GNU build omits the policy flag: ' + name)
            work_object = work / (name + '.os')
            old_object = str(build / 'dlfcn' / work_object.name)
            path = name + '.c'
            shape = recorded_command(pics, compiler, lambda line: ' ' + path + ' -c ' in line)
            changes = {path: str(copied / path), old_object: str(work_object),
                       old_object + '.dt': str(work_object) + '.dt'}
            command = [changes.get(word, word) for word in shape]
            command += ['-I', PORT / 'sysdeps/xos', MACRO,
                        '-ffile-prefix-map=' + str(work) + '=/xos-policy-delta',
                        '-ffile-prefix-map=' + str(ROOT) + '=/xos-policy-source']
            subprocess.run(command, cwd=source / 'dlfcn', check=True)
            members.append(work_object)

        changed = work / original.name
        shutil.copyfile(original, changed)
        subprocess.run(['x86_64-elf-ar', 'rD', changed, *members], check=True)
        subprocess.run(['x86_64-elf-ranlib', '-D', changed], check=True)
        before, after = read_archive(original), read_archive(changed)
        require(list(before) == list(after) and {name for name in before if before[name] != after[name]}
                == {item.name for item in members}, 'unexpected PIC archive changes')

        def link(label, pic_archive):
            directory = work / label
            directory.mkdir()
            prelinked = directory / 'libc_pic.os'
            clean = directory / 'libc_pic.os.clean'
            elf = directory / 'libc.so'
            changes = {str(original): str(pic_archive), str(build / 'libc_pic.os'): str(prelinked)}
            command = [changes.get(word, word) for word in commands['prelink']]
            subprocess.run(command, cwd=source, check=True)
            subprocess.run(['x86_64-elf-objcopy', '@' + str(options), prelinked, clean], check=True)
            changes = {str(build / 'libc_pic.os.clean'): str(clean), str(build / 'libc.so'): str(elf)}
            command = [changes.get(word, word) for word in commands['link']]
            subprocess.run(command, cwd=source / 'elf', check=True)
            return elf

        control = link('control', original)
        require(sha_file(control) == args.libc_sha256, 'PIC replay differs from the unchanged original libc')
        fixed = link('fixed', changed)
        destination = args.output / 'libc.so'
        shutil.copyfile(fixed, destination)
        result = {'status': 'linked', 'baseline_libc_sha256': args.libc_sha256,
                  'fixed_libc_sha256': sha_file(destination), 'rtld_sha256': sha_file(build / 'elf/ld.so'),
                  'baseline_archive_sha256': sha_file(original), 'changed_archive_sha256': sha_file(changed),
                  'fixed_objects': {item.name: sha_file(item) for item in members}, 'baseline_objects': inputs,
                  'pic_log_sha256': args.pic_log_sha256, 'link_log_sha256': args.link_log_sha256}
        (args.output / 'report.json').write_bytes(canonical(result))


if __name__ == '__main__':
    main()
