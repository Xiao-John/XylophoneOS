#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the authenticated GNU runtime, with an explicit public native startup mode."""

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import hashlib

from build_glibc_sdk import PORT, ROOT, sha
from build_glibc_shared_gcc import TARGET, configure_xos, rewrite
from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from verify_glibc_source import extract_verified_source, read_archive, verify_source
from verify_gcc_shared_source import read_lock as gcc_lock, verify_source as verify_gcc
from xypm_sdk_profile import inspect_sdk, metadata_snapshot, relative_file
from dynamic_artifacts import write_note
from build_glibc_terminal_support import input_paths as native_input_paths


# This is the existing native _dl_sysdep_start composition. The official
# dl-sysdep.os guard is separately compiled and must still reject SHARED.
RTLD_ROUTINES = ('$(all-dl-routines) dl-audit dl-compat dl-diagnostics '
                 'dl-diagnostics-cpu dl-diagnostics-kernel dl-environ dl-hwcaps '
                 'dl-hwcaps-subdirs dl-hwcaps_split dl-libc_freeres dl-minimal '
                 'dl-mutex dl-profile dl-usage rtld')
SHARED_FLAGS = ('-Wl,-shared,--hash-style=both,--eh-frame-hdr,-z,now,-z,relro,-z,noexecstack,'
                '-z,nomark-plt,-z,nopack-relative-relocs,-z,max-page-size=8192,-z,separate-code')
NATIVE_SOURCES = ('src/ports/glibc/terminal_support.cpp', 'src/user/sdk/terminal_client.cpp',
                  'src/user/arch/x86_64/syscall.cpp', 'src/user/loader/elf.cpp',
                  'src/ports/glibc/wait_support.cpp', 'src/ports/glibc/spawn_support.cpp',
                  'src/user/loader/load.cpp', 'src/user/sdk/file_client.cpp',
                  'src/user/sdk/text.cpp', 'src/user/arch/x86_64/tls.cpp')
PUBLIC_NATIVE_SOURCES = NATIVE_SOURCES + (
    'src/user/sdk/launch_control.cpp', 'src/user/loader/dynamic/identity.cpp',
    'src/user/loader/dynamic/generation.cpp', 'src/user/loader/dynamic/elf.cpp',
    'src/user/loader/dynamic/closure.cpp', 'src/user/loader/dynamic/startup.cpp',
    'src/user/loader/dynamic/spawn.cpp', 'src/user/loader/dynamic/rtld_control.cpp')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-build', 'glibc-archive', 'gcc-archive', 'gcc-signature', 'gcc-keyring', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--public-startup', action='store_true')
    parser.add_argument('--sdk-manifest-sha256')
    parser.add_argument('--sdk-tree-sha256')
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('output must be a new private directory')
    sdk = args.sdk_build.resolve(strict=True)
    binding = inspect_sdk('glibc', sdk)['binding']
    metadata, sdk_digest = metadata_snapshot(sdk / 'manifest.json')
    if binding['sdk_manifest_sha256'] != sdk_digest:
        raise ValueError('SDK manifest changed while selecting the build')
    if args.public_startup and (args.sdk_manifest_sha256 != sdk_digest
            or args.sdk_tree_sha256 != binding['sdk_tree_sha256']):
        raise ValueError('public startup requires both independent expected SDK manifest and full-tree digests')
    tools = {name: tool_identity('x86_64-elf-' + name) for name in (
        'gcc', 'g++', 'as', 'ld', 'ar', 'ranlib', 'nm', 'objcopy', 'objdump', 'readelf')}
    for name, tool in tools.items():
        if not tool.get('available') or tool['sha256'] != metadata['tools']['x86_64-elf-' + name]['sha256']:
            raise ValueError('target tool differs from the selected C SDK: ' + name)
    make = select_gnu_make()
    env, removed = clean_build_environment(os.environ)
    env.update(CONFIG_SITE='/dev/null', LC_ALL='C')
    output.mkdir(parents=True)
    original_sdk = sdk
    if args.public_startup:
        sdk = output / 'sdk_snapshot'
        sdk.mkdir()
        shutil.copytree(original_sdk / 'sysroot', sdk / 'sysroot', symlinks=False)
        shutil.copyfile(original_sdk / 'manifest.json', sdk / 'manifest.json')
        for directory in ('source_verification', 'gcc_source_verification'):
            if (original_sdk / directory).exists():
                shutil.copytree(original_sdk / directory, sdk / directory)
        if (inspect_sdk('glibc', sdk)['binding'] != binding
                or inspect_sdk('glibc', original_sdk)['binding'] != binding):
            raise ValueError('full SDK anchor changed before/after immutable build snapshot')
    recipe_paths = [ROOT / 'scripts' / name for name in (
        'build_glibc_shared_runtime.py', 'build_glibc_shared_gcc.py', 'build_glibc_sdk.py',
        'verify_glibc_source.py', 'verify_gcc_shared_source.py', 'glibc_g1_probe.py',
        'xypm_sdk_profile.py', 'xos_app.py', 'xypm_format.py', 'archive_member_map.py',
        'dynamic_artifacts.py', 'build_glibc_terminal_support.py')]
    recipe_paths += [ROOT / 'src/ports/gcc/shared_source_auth.json', ROOT / 'src/ports/gcc/source_lock.json']
    recipe_inputs = {path: sha(path) for path in recipe_paths}
    port_inputs = {path: sha(path) for path in PORT.rglob('*') if path.is_file()}
    report = {'status': 'building', 'scope': 'private_fixed_startup_closure',
              'sdk_binding': binding, 'tools': tools, 'make': make,
              'sanitized_environment': removed, 'steps': [],
              'guest_qualification': 'not_run', 'public_dynamic_sdk': False,
              'recipe_inputs': {str(path.relative_to(ROOT)): digest for path, digest in recipe_inputs.items()},
              'port_inputs': {str(path.relative_to(ROOT)): digest for path, digest in port_inputs.items()},
              'excluded_artifacts': ['sotruss-lib.so: audit is outside the fixed-closure profile']}
    if args.public_startup:
        report.update(scope='public_fixed_startup_closure', public_startup=True,
            native_abi=hashlib.sha256(('xos-glibc-dynamic-v1:' + sdk_digest).encode()).hexdigest(),
            expected_sdk_manifest_sha256=args.sdk_manifest_sha256,
            expected_sdk_tree_sha256=args.sdk_tree_sha256,
            sdk_snapshot='verified_before_and_after_full_copy')

    def save():
        (output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(label, argv, cwd=output, *, rejection=None):
        command = list(map(str, argv))
        log = output / (label + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
        report['steps'].append({'name': label, 'command': command, 'exit_code': result.returncode,
                                'log_sha256': sha(log)})
        save()
        text = log.read_text(errors='replace')
        if rejection is not None:
            if not result.returncode or rejection not in text:
                raise RuntimeError('official shared startup guard changed; see ' + str(log))
        elif result.returncode:
            raise RuntimeError(label + ' failed; see ' + str(log))
        print(label + ': ' + ('expected rejection' if rejection else 'passed'), flush=True)
        return text.strip()

    try:
        lock = json.loads((PORT / 'source_lock.json').read_bytes())
        archive = read_archive(args.glibc_archive, lock['archive_bytes'])
        verified = verify_source(args.glibc_archive, output / 'glibc_source_verification', archive_data=archive)
        if verified['archive_sha256'] != metadata['source_verification']['archive_sha256']:
            raise ValueError('GNU libc source differs from the selected C SDK')
        report['glibc_source_verification'] = verified
        extract_verified_source(archive, verified, output)
        del archive
        source = output / ('glibc-' + lock['version'])
        for patch in sorted((PORT / 'patches').glob('*.patch')):
            run('patch-' + patch.stem, ['patch', '-p1', '-i', patch], source)
        shutil.copytree(PORT / 'sysdeps', source / 'sysdeps', dirs_exist_ok=True)
        # GNU's lib pass also builds its hosted audit utility module. The
        # native startup profile explicitly rejects audit; it has no host
        # CRT and does not distribute that utility. Give this one output a
        # named opt-out without changing the runtime or its startup guard.
        elf_makefile = source / 'elf/Makefile'
        rewrite(elf_makefile, 'ifeq ($(build-shared),yes)\nextra-objs += sotruss-lib.os sotruss-lib.so',
                'ifeq ($(build-shared),yes)\nifneq ($(xos-private-fixed-closure),yes)\n'
                'extra-objs += sotruss-lib.os sotruss-lib.so')
        rewrite(elf_makefile, '\t$(do-install-program)\nendif\n\ntests-static-normal :=',
                '\t$(do-install-program)\nendif # xos-private-fixed-closure\nendif\n\ntests-static-normal :=')
        report['private_elf_makefile_sha256'] = sha(elf_makefile)
        if args.public_startup:
            # libc's hosted diagnostic executable is outside the native DSO
            # role. Remove that build input, rather than rewriting ELF bytes.
            rules = source / 'Makerules'
            rewrite(rules, '\t\t\t $(elf-objpfx)interp.os \\\n', '', count=2)
            report['public_makerules_sha256'] = sha(rules)
        report['source'] = source.name
        for name, tool in (('cc', 'gcc'), ('cxx', 'g++')):
            wrapper = output / name
            wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(tools[tool]['path'])
                               + ' --sysroot=' + shlex.quote(str(sdk / 'sysroot')) + ' "$@"\n')
            wrapper.chmod(0o755)

        # Build from the exact native support materials shipped by this SDK.
        if args.public_startup:
            native_paths = set(native_input_paths()) | {ROOT / name for name in PUBLIC_NATIVE_SOURCES}
            native_inputs = {str(path.relative_to(ROOT)): sha(path) for path in sorted(native_paths)}
            materials = output / 'native_inputs'
            sources = {}
            for name, expected in native_inputs.items():
                target = materials / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
                if sha(target) != expected:
                    raise ValueError('native source changed during snapshot: ' + name)
                sources[name] = target
            terminal_digest = hashlib.sha256(json.dumps(native_inputs, sort_keys=True).encode()).hexdigest()
            report['native_inputs'] = native_inputs
        else:
            terminal, terminal_digest = metadata_snapshot(sdk / 'terminal_support/manifest.json')
            materials = sdk / 'sysroot/usr/share/xos/terminal-support'
            sources = {name: relative_file(materials, name) for name in terminal['inputs']}
            if any(sha(path) != terminal['inputs'][name] or terminal['inputs'][name] != metadata['inputs'].get(name)
                   for name, path in sources.items()):
                raise ValueError('native support source materials changed')
        native = output / 'native_pic'
        native.mkdir()
        for name, path in sources.items():
            for prefix in ('src/shared/include/', 'src/user/include/'):
                if name.startswith(prefix):
                    destination = native / 'include' / name[len(prefix):]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists() and destination.read_bytes() != path.read_bytes():
                        raise ValueError('conflicting native support header')
                    shutil.copyfile(path, destination)
        # Receipts are data, never a source of executable command lines.
        flags = [tools['g++']['path'], '--sysroot=' + str(sdk / 'sysroot'), '-std=gnu++20',
                 '-O2', '-g', '-mno-red-zone', '-fPIC', '-fno-omit-frame-pointer', '-ffreestanding',
                 '-fno-builtin', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
                 '-fno-use-cxa-atexit', '-fno-stack-protector', '-ftls-model=initial-exec',
                 '-ffunction-sections', '-fdata-sections', '-fvisibility=hidden', '-nostdinc', '-nostdinc++',
                 '-I', native / 'include', '-isystem', sdk / 'sysroot/usr/include',
                 '-isystem', sdk / 'sysroot/usr/lib/compiler-include', '-Wall', '-Wextra', '-Werror']
        objects = []
        object_paths = {}
        for index, name in enumerate(PUBLIC_NATIVE_SOURCES if args.public_startup else NATIVE_SOURCES):
            if name not in sources:
                raise ValueError('selected SDK lacks native support source: ' + name)
            target = native / (str(index) + '_' + Path(name).stem + '.o')
            run('native-compile-' + str(index), [*flags, '-MMD', '-MF', str(target) + '.d',
                                                '-c', sources[name], '-o', target])
            objects.append(target)
            object_paths[name] = target
        native_archive = native / 'libxos_terminal_pic.a'
        run('native-archive', [tools['ar']['path'], 'rcsD', native_archive, *objects])
        report['native_support_manifest_sha256'] = terminal_digest
        public_flags = ''
        libc_identity = ''
        rtld_identity = ''
        if args.public_startup:
            for name, role in (('rtld', 2), ('libc', 4)):
                assembly, obj = native / (name + '_identity.S'), native / (name + '_identity.o')
                write_note(assembly, report['native_abi'], role)
                run('identity-' + name, [tools['gcc']['path'], '-c', assembly, '-o', obj])
            libc_identity = str(native / 'libc_identity.o') + ' '
            rtld_identity = ' '.join(map(str, (native / 'rtld_identity.o',
                object_paths['src/user/loader/dynamic/rtld_control.cpp'],
                object_paths['src/user/sdk/launch_control.cpp'],
                object_paths['src/user/arch/x86_64/syscall.cpp'])))
            public_flags = 'CPPFLAGS-config += -DXOS_PUBLIC_DYNAMIC_STARTUP\n'

        build = output / 'gnu'
        build.mkdir()
        env.update(CC=str(output / 'cc'), CXX=str(output / 'cxx'), CFLAGS='-O2 -g -mno-red-zone')
        env.update({key: tools[key.lower()]['path'] for key in (
            'AS', 'LD', 'AR', 'NM', 'RANLIB', 'OBJCOPY', 'OBJDUMP', 'READELF')})
        triplet = run('build-triplet', ['sh', source / 'scripts/config.guess'])
        run('configure', [source / 'configure', '--build=' + triplet, '--host=' + TARGET,
            '--prefix=/usr', '--disable-werror', '--enable-shared', '--enable-default-pie',
            '--disable-multi-arch', '--disable-mathvec', '--without-selinux', '--disable-nscd'], build)
        (build / 'configparms').write_text('ASFLAGS += -Wa,--divide\n' + public_flags
            + 'LDFLAGS.so += ' + SHARED_FLAGS + '\nLDFLAGS-rtld += ' + SHARED_FLAGS
            + ' ' + rtld_identity + '\nLDLIBS-c.so += ' + libc_identity + str(native_archive) + '\n')
        if not args.public_startup:
            run('official-shared-guard', [make['path'], '-C', source / 'elf', 'objdir=' + str(build),
                '-j1', build / 'elf/dl-sysdep.os'], rejection='XOS dynamic interpreter startup is not implemented')
        # Exclude the unshipped audit module, whose hosted GCC CRT is outside
        # this native composition. Do not silently accept a failing make lib.
        if args.public_startup:
            run('build-public-runtime', [make['path'], '-j' + str(args.jobs),
                'xos-private-fixed-closure=yes', 'lib'], build)
        else:
            run('build-private-runtime', [make['path'], '-j' + str(args.jobs),
                'rtld-routines=' + RTLD_ROUTINES, 'xos-private-fixed-closure=yes', 'lib'], build)
        if not (build / 'elf/ld.so.1').samefile(build / 'elf/ld.so'):
            raise ValueError('GNU interpreter SONAME alias differs from the built interpreter')

        # Rebuild GNU PIC CRT from the same authenticated GCC source as the
        # shared C++ libraries; bare-metal crtbegin.o is not an acceptable substitute.
        gcc_auth, _ = gcc_lock()
        archive = read_archive(args.gcc_archive, gcc_auth['archive_bytes'])
        verified = verify_gcc(args.gcc_archive, args.gcc_signature, args.gcc_keyring,
                              output / 'gcc_source_verification', archive_data=archive)
        report['gcc_source_verification'] = verified
        crt = output / 'pic_crt'
        crt.mkdir()
        extract_verified_source(archive, verified, crt)
        del archive
        gcc_source = crt / ('gcc-' + gcc_auth['version'])
        configure_xos(gcc_source)
        gcc, target = crt / 'gcc', crt / 'target/libgcc'
        gcc.mkdir()
        target.mkdir(parents=True)
        env, _ = clean_build_environment(env)
        env.update(CC=tools['gcc']['path'], CFLAGS='-O2 -g0', CONFIG_SITE='/dev/null', LC_ALL='C')
        env.update({name.upper(): tools[name]['path'] for name in ('ar', 'ranlib', 'ld', 'nm')})
        gcc_triplet = run('gcc-build-triplet', [gcc_source / 'config.guess'])
        run('configure-pic-crt', [gcc_source / 'libgcc/configure', '--build=' + gcc_triplet,
            '--host=' + TARGET, '--enable-shared', '--disable-gcov'], target)
        env.update(TARGET_CPU_DEFAULT='', HEADERS='auto-host.h ansidecl.h', DEFINES='USED_FOR_TARGET')
        run('crt-target-headers', ['sh', gcc_source / 'gcc/mkconfig.sh', 'tconfig.h'], gcc)
        for name in ('TARGET_CPU_DEFAULT', 'HEADERS', 'DEFINES'):
            del env[name]
        plugin = Path(run('gcc-plugin', [tools['gcc']['path'], '-print-file-name=plugin'])) / 'include'
        (gcc / 'libgcc.mvars').write_text('GCC_CFLAGS = -I' + str(plugin)
            + ' -DIN_GCC -DGTHREAD_USE_WEAK=0\nINHIBIT_LIBC_CFLAGS = -Dinhibit_libc\n')
        make_crt = [make['path'], '-j' + str(args.jobs), 'gcc_objdir=' + str(gcc),
                    'LIBGCC2_DEBUG_CFLAGS=-g0']
        run('crt-config-header', [*make_crt, 'libgcc_tm.h'], target)
        run('build-pic-crt', [*make_crt, 'crtbeginS.o', 'crtendS.o'], target)
        for name in ('libc.so', 'elf/ld.so'):
            text = run('inspect-' + Path(name).name, [tools['readelf']['path'], '-hW', '-lW', '-dW', build / name])
            if ('DYN (Shared object file)' not in text or 'GNU_RELRO' not in text
                    or 'GNU_EH_FRAME' not in text or '(TEXTREL)' in text
                    or '(RPATH)' in text or '(RUNPATH)' in text):
                raise ValueError('unexpected native shared ELF: ' + name)
        files = [build / name for name in ('libc.so', 'elf/ld.so', 'elf/xos_file_session.os',
                  'csu/Scrt1.o', 'csu/crti.o', 'csu/crtn.o')]
        files += [target / name for name in ('crtbeginS.o', 'crtendS.o')]
        files += [native_archive]
        report['artifacts'] = {str(path.relative_to(output)): sha(path) for path in files}
        if (inspect_sdk('glibc', sdk)['binding'] != binding
                or inspect_sdk('glibc', original_sdk)['binding'] != binding):
            raise ValueError('selected C SDK changed during the build')
        if any(sha(path) != digest for path, digest in (recipe_inputs | port_inputs).items()):
            raise ValueError('recipe or native port changed during the build')
        if args.public_startup and any(sha(ROOT / name) != value for name, value in native_inputs.items()):
            raise ValueError('public native support inputs changed during build')
        if any(sha(Path(tool['path'])) != tool['sha256'] for tool in tools.values()):
            raise ValueError('target tool changed during the build')
        for path, digest in ((args.glibc_archive, report['glibc_source_verification']['archive_sha256']),
                             (args.gcc_archive, verified['archive_sha256']),
                             (args.gcc_signature, verified['signature_sha256']),
                             (args.gcc_keyring, verified['keyring_sha256'])):
            if sha(path) != digest:
                raise ValueError('authenticated source input changed during the build')
        report['status'] = 'public_runtime_built_not_run' if args.public_startup else 'private_runtime_built_not_run'
        save()
    except BaseException as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        save()
        raise


if __name__ == '__main__':
    main()
