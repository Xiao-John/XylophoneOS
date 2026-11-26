#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build native, versioned GCC DSOs for the private XOS GNU startup composition."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

from build_glibc_sdk import ROOT, sha
from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from xypm_sdk_profile import inspect_sdk

SOURCE_LOCK = ROOT / 'src/ports/gcc/source_lock.json'
DRIVER = ROOT / 'scripts/glibc_shared_gcc_driver.sh'
SIGNATURE_SHA = '43d73202dcede15d31001c6ba0d28723014ef57e4dc815631772daadbe23bcd2'
KEYRING_SHA = '8013de59880f7a59f53b6bd207f4d2a408d67b84a82fa9cba1dbbf443428e2db'
SIGNING_FINGERPRINT = '7F74F97C103468EE5D750B583AB00996FC26A641'
PRIMARY_FINGERPRINT = '13975A70E63C361C73AE69EF6EEB81F8981C74C7'
TARGET = 'x86_64-unknown-xos'
LIBGCC, LIBM, LIBSTD = 'libgcc_s.so.1', 'libm.so.0.1', 'libstdc++.so.6'
LIBC, RTLD = 'libc.so.0.1', 'ld.so.1'


def rewrite(path, old, new, count=1):
    text = path.read_text()
    if text.count(old) != count:
        raise RuntimeError(f'upstream source anchor changed in {path.name}: {old!r}')
    path.write_text(text.replace(old, new))


def configure_xos(source):
    rewrite(source / 'config.sub', '| fiwix* )', '| fiwix* | xos )')
    rewrite(source / 'libgcc/config.host', 'x86_64-*-elf* | x86_64-*-rtems*)', '''x86_64-*-xos)
        tmake_file="$tmake_file i386/t-crtstuff t-crtstuff-pic t-libgcc-pic t-eh-dw2-dip"
        tmake_file="$tmake_file t-slibgcc t-slibgcc-gld t-slibgcc-elf-ver"
        ;;
x86_64-*-elf* | x86_64-*-rtems*)''')
    # XOS uses the upstream cross compiler, linker and native libc probes.
    # GNU userspace naming, hardware probes and ABI baselines remain separate.
    case_start = '*-linux* | *-uclinux* | *-gnu* | *-kfreebsd*-gnu | *-cygwin* | *-solaris*)'
    for relative in ('crossconfig.m4', 'configure'):
        path = source / 'libstdc++-v3' / relative
        text = path.read_text()
        start = text.index(case_start)
        end = text.index('\n    ;;', start)
        original = text[start:end]
        native = original.replace(case_start, '*-xos | ' + case_start)
        native = re.sub(r'^.*(?:AC_DEFINE\(|#define )_GLIBCXX_USE_(?:DEV_RANDOM|RANDOM_TR1)\b.*$',
                        r'    if test "$host_os" != xos; then\n\g<0>\n    fi', native, flags=re.M)
        rewrite(path, original, native)
    # Libtool's ELF numeric-version naming mode is named "linux". XOS uses
    # that SONAME naming algorithm with its own interpreter and file policy.
    case_old = 'linux* | k*bsd*-gnu | kopensolaris*-gnu | gnu* | uclinuxfdpiceabi)'
    case_new = '''xos)
  version_type=linux
  need_lib_prefix=no
  need_version=no
  library_names_spec='$libname$release$shared_ext$versuffix $libname$release$shared_ext$major $libname$shared_ext'
  soname_spec='$libname$release$shared_ext$major'
  dynamic_linker='XOS GNU ELF ld.so'
  shlibpath_overrides_runpath=no
  hardcode_into_libs=no
  ;;
''' + case_old
    for relative, cases in (('libtool.m4', 1), ('libstdc++-v3/configure', 2)):
        path = source / relative
        rewrite(path, case_old, case_new, cases)
        pattern = 'linux* | k*bsd*-gnu | kopensolaris*-gnu | uclinuxfdpiceabi)'
        rewrite(path, pattern, 'xos | ' + pattern)
        pattern = '      linux* | k*bsd*-gnu | kopensolaris*-gnu)\n        case $cc_basename in'
        rewrite(path, pattern, pattern.replace('      linux*', '      xos | linux*'))


def elf_record(readelf, path, soname, env, output):
    text = subprocess.check_output([readelf, '-hW', '-lW', '-dW', '-VW', '-sW', path], env=env, text=True)
    (output / f'{soname}.readelf.log').write_text(text)
    needed = re.findall(r'Shared library: \[([^\]]+)\]', text)
    stack = [line for line in text.splitlines() if line.strip().startswith('GNU_STACK')]
    if ('DYN (Shared object file)' not in text or 'Advanced Micro Devices X86-64' not in text
            or f'Library soname: [{soname}]' not in text or '(RPATH)' in text or '(RUNPATH)' in text
            or 'GNU_RELRO' not in text or 'GNU_EH_FRAME' not in text or 'Flags: NOW' not in text
            or len(stack) != 1 or stack[0].split()[-2] != 'RW'):
        raise RuntimeError(f'invalid target shared ELF properties for {soname}')
    return {'needed': needed, 'sha256': sha(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'signature', 'keyring', 'sdk-build', 'glibc-source', 'gnu-build', 'pic-crt', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    sdk_build = args.sdk_build.resolve(strict=True)
    gnu_build = args.gnu_build.resolve(strict=True)
    output = args.output.absolute()
    output.mkdir(parents=True)
    locks = json.loads(SOURCE_LOCK.read_bytes())
    bindings = {args.archive: locks['sha256'], args.signature: SIGNATURE_SHA, args.keyring: KEYRING_SHA}
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError(f'GCC source input digest differs: {path}')
    sdk_path = sdk_build / 'manifest.json'
    sdk = json.loads(sdk_path.read_bytes())
    sdk_binding = inspect_sdk('glibc', sdk_build)['binding']
    libc, interpreter = gnu_build / 'libc.so', gnu_build / 'elf/ld.so'
    original = {file: sha(file) for file in (
        sdk_path, libc, interpreter, *(gnu_build / 'csu' / name for name in ('Scrt1.o', 'crti.o', 'crtn.o')),
        *(args.pic_crt / name for name in ('crtbeginS.o', 'crtendS.o')))}
    tools = {name: tool_identity('x86_64-elf-' + name) for name in (
        'gcc', 'g++', 'as', 'ld', 'ar', 'ranlib', 'nm', 'objdump', 'strip', 'readelf')}
    for name, info in tools.items():
        previous = sdk['tools'].get('x86_64-elf-' + name)
        if not info.get('available') or (name != 'strip' and info['sha256'] != previous['sha256']):
            raise ValueError(f'GCC tool differs from the glibc SDK: {name}')
    env, removed = clean_build_environment(os.environ)
    work = output / 'work'
    scratch, target_tools, link, std, libgcc, gcc = (work / name for name in (
        'tmp', 'tools', 'link', 'std', 'target/libgcc', 'gcc'))
    for path in (scratch, target_tools, link, std, libgcc, gcc, work / 'libgcc'):
        path.mkdir(parents=True)
    env.update(LC_ALL='C', CONFIG_SITE='/dev/null', TMPDIR=str(scratch))
    commands = {}

    def run(name, argv, cwd=work):
        command = list(map(str, argv))
        commands[name] = command
        log = output / f'{name}.log'
        with log.open('w') as stream:
            subprocess.run(command, env=env, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
        return log.read_text(errors='replace')

    gpg_status = run('signature', ['gpgv', '--keyring', args.keyring.resolve(), '--status-fd', '1',
                                  args.signature.resolve(), args.archive.resolve()])
    matches = [line.split() for line in gpg_status.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    if (len(matches) != 1 or matches[0][2] != SIGNING_FINGERPRINT or matches[0][-1] != PRIMARY_FINGERPRINT
            or re.search(r'^\[GNUPG:\] (BADSIG|ERRSIG|EXPKEYSIG|REVKEYSIG|KEYEXPIRED|SIGEXPIRED|EXPSIG)\b',
                         gpg_status, re.M)):
        raise ValueError('GCC upstream signature status or fingerprint differs')
    with tarfile.open(args.archive) as archive:
        archive.extractall(work, filter='data')
    version = locks['version']
    source = work / ('gcc-' + version)
    configure_xos(source)
    triplet = run('build-triplet', [source / 'config.guess']).strip()
    if run('target-triplet', [source / 'config.sub', TARGET]).strip() != TARGET:
        raise ValueError('XOS GCC source did not recognize the native target')
    make = select_gnu_make()['path']
    jobs = f'-j{args.jobs}'
    glibc = args.glibc_source.resolve(strict=True)
    atexit = gnu_build / 'stdlib/atexit.oS'
    run('glibc-atexit', [make, '-C', glibc / 'stdlib', 'objdir=' + str(gnu_build), jobs, atexit])

    for name in ('as', 'ld'):
        (target_tools / name).symlink_to(tools[name]['path'])
    local_driver = target_tools / 'driver'
    shutil.copyfile(DRIVER, local_driver)
    local_driver.chmod(0o755)
    for name in ('cc', 'cxx'):
        (target_tools / name).symlink_to('driver')
    for name, path in ((LIBC, libc), ('libc.so', libc), (RTLD, interpreter)):
        (link / name).symlink_to(path)
    env.update(XOS_TARGET_CC=tools['gcc']['path'], XOS_TARGET_CXX=tools['g++']['path'],
               XOS_C_SYSROOT=str(sdk_build / 'sysroot'), XOS_GCC_TOOLS=str(target_tools),
               XOS_SHARED_GLIBC=str(gnu_build), XOS_GCC_PIC_CRT=str(args.pic_crt.resolve(strict=True)),
               XOS_GCC_LINK=str(link), CC=str(target_tools / 'cc'), CXX=str(target_tools / 'cxx'),
               CFLAGS='-O2 -g0', CXXFLAGS='-O2 -g0', gcc_cv_target_thread_file='posix')
    env.update({name.upper(): tools[name]['path'] for name in ('ar', 'ranlib', 'ld', 'nm', 'objdump', 'strip')})
    plugin = Path(run('gcc-plugin-directory', [tools['gcc']['path'], '-print-file-name=plugin']).strip()) / 'include'
    run('configure-libgcc', [source / 'libgcc/configure', f'--build={triplet}', f'--host={TARGET}',
                             '--enable-shared', '--disable-gcov'], libgcc)
    env.update(TARGET_CPU_DEFAULT='', HEADERS='auto-host.h ansidecl.h', DEFINES='USED_FOR_TARGET')
    run('gcc-target-headers', ['sh', source / 'gcc/mkconfig.sh', 'tconfig.h'], gcc)
    for key in ('TARGET_CPU_DEFAULT', 'HEADERS', 'DEFINES'):
        del env[key]
    (gcc / 'libgcc.mvars').write_text(
        f'GCC_CFLAGS = -I{plugin} -DIN_GCC -DGTHREAD_USE_WEAK=0\nINHIBIT_LIBC_CFLAGS =\n')
    run('build-libgcc', [make, jobs, 'gcc_objdir=' + str(gcc), 'SHLIB_LC=-lc',
                         'LIBGCC2_DEBUG_CFLAGS=-g0', 'libgcc_s.so'], libgcc)
    gcc_dso = libgcc / LIBGCC
    (link / LIBGCC).symlink_to(gcc_dso)
    (link / 'libgcc_s.so').symlink_to(gcc_dso)
    # Restore the exact glibc build's compiler configuration for its make
    # targets. In particular, avoid injecting the C++ libtool driver.
    gcc_env = dict(env)
    env, _ = clean_build_environment(env)
    math = gnu_build / 'math/libm.so'
    math_flags = ('LDFLAGS-m.so=-nostdlib -Wl,-shared,--eh-frame-hdr,-z,now,-z,relro,-z,noexecstack,'
                  '-z,nomark-plt,-z,nopack-relative-relocs,-z,max-page-size=8192,-z,separate-code')
    run('build-libm', [make, '-C', glibc / 'math', 'objdir=' + str(gnu_build), jobs,
                      '-o', libc, '-o', interpreter,
                      f'link-libc-deps={libc} {interpreter} {gcc_dso}',
                      f'link-libc-args={libc} -Wl,--as-needed {gcc_dso} {interpreter}', math_flags, math])
    env = gcc_env
    (link / LIBM).symlink_to(math)
    (link / 'libm.so').symlink_to(math)
    (work / 'libgcc/gthr-default.h').symlink_to(source / 'libgcc/gthr-posix.h')
    index = f'include/c++/{version}'
    configured = run('configure-libstdcxx', [source / 'libstdc++-v3/configure', f'--build={triplet}',
                     f'--host={TARGET}', '--prefix=/usr', f'--with-gxx-include-dir=/usr/{index}',
                     '--disable-multilib', '--enable-shared', '--disable-static', '--disable-nls',
                     '--disable-libstdcxx-pch', '--enable-libstdcxx-threads=yes', '--enable-clocale=generic',
                     '--disable-libstdcxx-backtrace', '--disable-libstdcxx-filesystem-ts'], std)
    cfg = (std / 'config.h').read_text()
    if ('checking for shared libgcc... yes' not in configured
            or '#define HAVE___CXA_THREAD_ATEXIT_IMPL 1' not in cfg
            or '#define _GLIBCXX_HAS_GTHREADS 1' not in cfg):
        raise RuntimeError('libstdc++ target feature checks differ from the qualified configuration')
    run('build-libstdcxx', [make, jobs], std)
    for directory in ('include', 'libsupc++'):
        run('install-headers-' + directory.replace('+', 'x'),
            [make, '-C', std / directory, 'install' if directory == 'include' else 'install-data',
             'DESTDIR=' + str(work / 'install')])
    shutil.copytree(work / 'install/usr/include', output / 'include')
    licenses = output / 'licenses'
    licenses.mkdir()
    for name in ('COPYING3', 'COPYING.RUNTIME'):
        shutil.copyfile(source / name, licenses / name)
    pkg_lib = output / 'lib'
    pkg_lib.mkdir()
    for name, file in ((LIBGCC, gcc_dso), (LIBM, math), (LIBSTD, std / 'src/.libs' / LIBSTD), ('atexit.oS', atexit)):
        shutil.copyfile(file, pkg_lib / name)
    elf = {name: elf_record(tools['readelf']['path'], pkg_lib / name, name, env, output)
           for name in (LIBGCC, LIBM, LIBSTD)}
    expected = {LIBGCC: {LIBC}, LIBM: {LIBC, LIBGCC}, LIBSTD: {LIBM, LIBGCC, LIBC, RTLD}}
    if any(set(elf[name]['needed']) != libraries for name, libraries in expected.items()):
        raise RuntimeError('GCC runtime has an unexpected shared dependency graph')
    for path, digest in (original | bindings).items():
        if sha(path) != digest:
            raise ValueError(f'bound build input changed: {path}')
    manifest = {'status': 'built_not_run', 'target': TARGET, 'gcc_release': version,
                'source_archive_sha256': bindings[args.archive], 'signature_sha256': SIGNATURE_SHA,
                'keyring_sha256': KEYRING_SHA, 'signing_fingerprint': SIGNING_FINGERPRINT,
                'primary_fingerprint': PRIMARY_FINGERPRINT, 'sdk_manifest_sha256': original[sdk_path],
                'sdk_tree_sha256': sdk_binding['sdk_tree_sha256'], 'libc_sha256': original[libc],
                'interpreter_sha256': original[interpreter],
                'include_directories': [index, f'{index}/{TARGET}', f'{index}/backward'],
                'artifacts': {p.name: sha(p) for p in sorted(pkg_lib.iterdir())},
                'headers': {str(p.relative_to(output)): sha(p) for p in sorted((output / 'include').rglob('*'))
                            if p.is_file()}, 'elf': elf, 'tools': tools, 'commands': commands,
                'sanitized_environment': removed, 'bound_inputs': {str(p): digest for p, digest in original.items()},
                'recipe_sha256': sha(Path(__file__)), 'driver_sha256': sha(DRIVER),
                'plugin_headers': {name: sha(plugin / name) for name in ('auto-host.h', 'tm.h', 'tsystem.h', 'coretypes.h')}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
