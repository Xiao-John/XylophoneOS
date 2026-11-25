#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the isolated static XOS glibc research SDK from its locked source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile

from glibc_g1_probe import clean_build_environment, tool_identity
from verify_glibc_source import extract_verified_source, read_archive, verify_source
from build_glibc_terminal_support import input_paths as terminal_inputs

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/glibc'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inputs():
    paths = [p for p in sorted(PORT.rglob('*')) if p.is_file()]
    paths.extend(ROOT / 'scripts' / name for name in
                 ('build_glibc_sdk.py', 'build_glibc_program.py',
                  'glibc_g1_probe.py', 'glibc_g1_deps.py', 'verify_glibc_source.py'))
    paths.extend(terminal_inputs())
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}


def install_stub_header(source, sysroot, env):
    """Use the upstream stub sections, excluding non-SDK utility programs."""
    archives = sorted((sysroot / 'usr/lib').glob('*.a'))
    sections = subprocess.check_output(
        ['x86_64-elf-objdump', '-h', *map(str, archives)], env=env, text=True)
    stubs = sorted(set(re.findall(r'\.gnu\.glibc-stub\.([A-Za-z0-9_]+)', sections)))
    if not stubs:
        raise RuntimeError('static library stub section extraction was empty')
    prologue = (source / 'include/stubs-prologue.h').read_text()
    header = '\n'.join(line for line in prologue.splitlines()
                       if not line.startswith('@')) + '\n'
    header += ''.join('#define __stub_' + name + '\n' for name in stubs)
    (sysroot / 'usr/include/gnu/stubs.h').write_text(header)
    return stubs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 64:
        parser.error('jobs must be in 1..64')
    archive = args.archive.resolve(strict=True)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new private directory')
    lock = json.loads((PORT / 'source_lock.json').read_text())
    if sha(archive) != lock['archive_sha256']:
        parser.error('source archive SHA-256 mismatch')
    env, removed = clean_build_environment(os.environ)
    env['CONFIG_SITE'] = '/dev/null'
    env['LC_ALL'] = 'C'
    names = ['x86_64-elf-gcc', 'x86_64-elf-g++', 'x86_64-elf-ld',
             'x86_64-elf-as', 'x86_64-elf-ar', 'x86_64-elf-readelf',
             'x86_64-elf-objdump', 'x86_64-elf-objcopy', 'x86_64-elf-nm',
             'x86_64-elf-ranlib', 'gcc', 'python3', 'make', 'gawk', 'bison', 'patch', 'gpgv']
    tools = {name: tool_identity(name) for name in names}
    missing = [name for name in names if not tools[name]['available']]
    if missing:
        parser.error('missing tools: ' + ', '.join(missing))
    output.mkdir(parents=True)
    report = {'status': 'building', 'profile': 'xos_glibc_static_research_v1',
              'process_exit_cleanup': {'syscall': 51, 'mode': 1, 'request_version': 1,
                                       'deadline_ns': 30000000000, 'timeout_status': 127},
              'source_sha256': sha(archive),
              'source_authentication': lock['signature_verification'],
              'tools': tools, 'sanitized_environment': removed,
              'inputs': inputs(),
              'steps': [], 'guest_qualification': 'not_run'}

    def save():
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(name, command, cwd):
        log = output / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=cwd, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT)
        report['steps'].append({'name': name, 'command': command,
                                'exit_code': result.returncode, 'log_sha256': sha(log)})
        save()
        if result.returncode != 0:
            raise RuntimeError(name + ' failed; see ' + str(log))

    def check_inputs():
        if inputs() != report['inputs'] or sha(archive) != report['source_sha256']:
            raise RuntimeError('build input files changed during compilation')
        if any(sha(Path(item['path'])) != item['sha256'] for item in tools.values()):
            raise RuntimeError('selected tool binary changed during compilation')

    try:
        archive_data = read_archive(archive, lock['archive_bytes'])
        report['source_verification'] = verify_source(
            archive, output / 'source_verification', gpgv=tools['gpgv']['path'], archive_data=archive_data)
        if report['source_verification']['verifier']['sha256'] != tools['gpgv']['sha256']:
            raise RuntimeError('source verifier differs from the selected build tool')
        report['source_verification_report_sha256'] = sha(output / 'source_verification/report.json')
        save()
        extract_verified_source(archive_data, report['source_verification'], output)
        del archive_data
        source = output / ('glibc-' + lock['version'])
        for patch in sorted((PORT / 'patches').glob('*.patch')):
            run('patch-' + patch.stem, ['patch', '-p1', '-i', str(patch)], source)
        shutil.copytree(PORT / 'sysdeps', source / 'sysdeps', dirs_exist_ok=True)
        build = output / 'configure'
        build.mkdir()
        sysroot = output / 'sysroot'
        sysroot.mkdir()
        for name, tool in [('cc', 'x86_64-elf-gcc'), ('cxx', 'x86_64-elf-g++')]:
            wrapper = output / name
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(shutil.which(tool))
                               + ' --sysroot=' + shlex.quote(str(sysroot)) + ' "$@"\n')
            wrapper.chmod(0o755)
        env['CC'] = str(output / 'cc')
        env['CXX'] = str(output / 'cxx')
        for variable in ('AS', 'LD', 'AR', 'NM', 'RANLIB', 'OBJCOPY', 'OBJDUMP', 'READELF'):
            env[variable] = shutil.which('x86_64-elf-' + variable.lower())
        env['CFLAGS'] = '-O2 -g -mno-red-zone'
        triplet = subprocess.check_output(['sh', str(source / 'scripts/config.guess')],
                                         text=True, env=env).strip()
        report['host_build_triplet'] = triplet
        command = [str(source / 'configure'), '--build=' + triplet,
                   '--host=x86_64-unknown-xos', '--prefix=/usr', '--disable-werror',
                   '--disable-shared', '--disable-default-pie', '--disable-multi-arch',
                   '--disable-mathvec', '--without-selinux', '--disable-nscd']
        run('configure', command, build)
        # The bare-metal ELF assembler treats '/' as a comment by default;
        # glibc's x86 assembly requires GAS division expressions.
        (build / 'configparms').write_text('ASFLAGS += -Wa,--divide\n')
        if args.prepare_only:
            check_inputs()
            report['status'] = 'configured'
            save()
            return
        run('make-lib', ['make', '-j' + str(args.jobs), 'lib'], build)
        # Distinct top-level recursive make goals do not share their job or
        # dependency graph.  Combining them races generated headers and .o.T
        # files in glibc.  Install each phase serially after the parallel build.
        run('install-headers', ['make', '-j1', 'install-headers',
                                'DESTDIR=' + str(sysroot)], build)
        run('install-lib', ['make', '-j1', 'install-lib',
                            'DESTDIR=' + str(sysroot)], build)
        libdir = sysroot / 'usr/lib'
        # Upstream attaches libc.a to the full install target, separately
        # from install-lib.  Copy the just-built archive without requesting
        # locale, timezone or dynamic-loader utility executables.
        shutil.copyfile(build / 'libc.a', libdir / 'libc.a')
        shutil.copyfile(build / 'gnu/lib-names.h', sysroot / 'usr/include/gnu/lib-names.h')
        for required in ['libc.a', 'libm.a', 'crti.o', 'crtn.o']:
            if not (libdir / required).is_file():
                raise RuntimeError('missing installed target library: ' + required)
        report['stub_functions'] = install_stub_header(source, sysroot, env)
        compiler_headers = Path(subprocess.check_output(
            ['x86_64-elf-gcc', '-print-file-name=include'],
            text=True, env=env).strip()).resolve(strict=True)
        report['compiler_headers_source'] = str(compiler_headers)
        shutil.copytree(compiler_headers, libdir / 'compiler-include')
        report['compiler_runtime'] = {}
        for name in ('libgcc.a', 'libgcc_eh.a', 'crtbegin.o', 'crtend.o'):
            origin_name = subprocess.check_output(
                ['x86_64-elf-gcc', '-print-file-name=' + name],
                env=env, text=True).strip()
            # Some bare-metal GCC builds package the unwinder in libgcc.a.
            if name == 'libgcc_eh.a' and origin_name == name:
                report['compiler_runtime'][name] = {'available': False}
                continue
            origin = Path(origin_name).resolve(strict=True)
            if not origin.is_file():
                raise RuntimeError('missing compiler runtime: ' + name)
            shutil.copyfile(origin, libdir / name)
            report['compiler_runtime'][name] = {'path': str(origin),
                                                 'sha256': sha(origin)}
        for stem, source_name in [('xos_start', 'start.S'), ('xos_start_c', 'start.c')]:
            run('crt-' + stem, [env['CC'], '-O2', '-g', '-mno-red-zone', '-fno-pie',
                               '-fno-stack-protector', '-fno-builtin', '-nostdinc',
                               '-isystem', str(sysroot / 'usr/include'),
                               '-isystem', str(libdir / 'compiler-include'),
                               '-c', str(PORT / 'crt' / source_name),
                               '-o', str(libdir / (stem + '.o'))], build)
        run('terminal-support', ['python3', str(ROOT / 'scripts/build_glibc_terminal_support.py'),
                                 '--sdk', str(sysroot), '--output', str(output / 'terminal_support')], ROOT)
        shutil.copyfile(PORT / 'crt/user.ld', sysroot / 'user.ld')
        materials = sysroot / 'usr/share/xos-glibc'
        materials.mkdir(parents=True)
        for name in ('COPYING', 'COPYING.LIB', 'LICENSES'):
            if (source / name).is_file():
                shutil.copyfile(source / name, materials / name)
        compiler_licenses = materials / 'compiler-runtime-licenses'
        compiler_licenses.mkdir()
        compiler_prefix = Path(tools['x86_64-elf-gcc']['path']).parent.parent
        for name in ('COPYING', 'COPYING.LIB', 'COPYING.RUNTIME'):
            origin = compiler_prefix / name
            if not origin.is_file():
                raise RuntimeError('missing compiler runtime license: ' + str(origin))
            shutil.copyfile(origin, compiler_licenses / name)
        shutil.copytree(PORT, materials / 'port')
        (materials / 'scripts').mkdir()
        for name in ('build_glibc_sdk.py', 'build_glibc_program.py',
                     'glibc_g1_probe.py', 'glibc_g1_deps.py', 'verify_glibc_source.py',
                     'build_glibc_terminal_support.py'):
            shutil.copyfile(ROOT / 'scripts' / name, materials / 'scripts' / name)
        (materials / 'provenance.json').write_text(json.dumps({
            'source': lock, 'source_verification': report['source_verification'],
            'source_verification_report_sha256': report['source_verification_report_sha256'],
            'inputs': report['inputs'],
            'patch_order': [str(p.relative_to(ROOT))
                            for p in sorted((PORT / 'patches').glob('*.patch'))],
            'tools': tools, 'compiler_runtime': report['compiler_runtime'],
            'scope': 'static libraries and C headers; libc utilities excluded',
        }, indent=2) + '\n')
        check_inputs()
        report['artifacts'] = {str(p.relative_to(sysroot)): sha(p)
                               for p in sorted(sysroot.rglob('*')) if p.is_file()}
        report['status'] = 'static_sdk_built'
        save()
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
