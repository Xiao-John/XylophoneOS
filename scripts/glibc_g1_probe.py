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
        overlay = ROOT / 'src/ports/glibc/sysdeps/xos'
        for path in sorted(overlay.rglob('*')):
            if path.is_file():
                destination = marker / path.relative_to(overlay)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
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
            make_result = subprocess.run(['gnumake', '-j4'], cwd=build, env=env, stdout=log, stderr=subprocess.STDOUT)
    objects = {}
    if backend and make_result is not None:
        for subdir, name in (('stdlib', 'abs'), ('posix', '_exit')):
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
              'header_install': header_install,
              'xos_overlay_sha256': {str(p.relative_to(ROOT / 'src/ports/glibc/sysdeps/xos')): digest(p) for p in (ROOT / 'src/ports/glibc/sysdeps/xos').rglob('*') if p.is_file()},
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
