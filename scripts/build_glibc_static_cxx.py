#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the qualified static POSIX C++ runtime against one authenticated C SDK."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from archive_member_map import read_archive as archive_members
from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from verify_gcc_shared_source import read_archive, read_lock, verify_source, extract_verified_source
from verify_glibc_source import check_status, digest as sha
from xypm_sdk_profile import (GLIBC_UNWINDER_MEMBERS, GLIBC_UNWINDER_SYMBOLS,
                              inspect_sdk, sdk_snapshot, strong_undefined_symbols)

ROOT = Path(__file__).resolve().parents[1]
FEATURES = ('directories', 'stdio_transfer', 'threads')
TARGET = 'x86_64-unknown-xos'
RECIPE = ROOT / 'docs/reports/glibc_stock_fork_sdk_20261126'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def configure_source(source):
    """The already qualified static recipe, with strict upstream anchors."""
    path = source / 'config.sub'
    text = path.read_text()
    anchor = '| fiwix* )'
    require(text.count(anchor) == 1, 'GCC config.sub anchor changed')
    path.write_text(text.replace(anchor, '| fiwix* | xos )'))
    host = '*-linux* | *-uclinux* | *-gnu* | *-kfreebsd*-gnu | *-cygwin* | *-solaris*)'
    for name in ('crossconfig.m4', 'configure'):
        path = source / 'libstdc++-v3' / name
        text = path.read_text()
        require(text.count(host) == 1, 'GCC cross configuration anchor changed')
        start = text.index(host)
        end = text.index('\n    ;;', start)
        case = text[start:end].replace(host, '*-xos | ' + host)
        case = re.sub(r'^.*(?:AC_DEFINE\(|#define )_GLIBCXX_USE_(?:DEV_RANDOM|RANDOM_TR1)\b.*$',
                      r'    if test "$host_os" != xos; then\n\g<0>\n    fi', case, flags=re.M)
        path.write_text(text[:start] + case + text[end:])


def write_driver(path, sdk, tools):
    # Generate argv, never shell code containing caller-controlled paths.
    source = '''#!/usr/bin/env python3
import os
from pathlib import Path
import sys
sdk = Path(SDK)
tools = TOOLS
lib = sdk / 'usr/lib'
cxx = Path(sys.argv[0]).name == 'cxx'
flags = ['-B' + str(Path(__file__).resolve().parent) + '/', '--sysroot=' + str(sdk),
         '-nostdinc', '-isystem', str(sdk / 'usr/include'), '-isystem', str(lib / 'compiler-include'),
         '-mno-red-zone', '-ftls-model=local-exec', '-fno-pie']
if cxx: flags.append('-nostdinc++')
args = sys.argv[1:]
compile_only = any(a in ('-c', '-S', '-E', '-M', '-MM', '-fsyntax-only', '--version', '-v')
                   or a.startswith(('-dump', '-print')) for a in args)
compiler = tools['g++' if cxx else 'gcc']['path']
if compile_only:
    command = [compiler, *flags, *args]
else:
    start = ['xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o']
    libraries = ['libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a']
    command = [compiler, *flags, '-static', '-no-pie', '-nostdlib',
               '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T' + str(sdk / 'user.ld'),
               *(str(lib / n) for n in start), *args, '-Wl,--start-group',
               *(str(lib / n) for n in libraries), '-Wl,--end-group',
               str(lib / 'crtend.o'), str(lib / 'crtn.o')]
os.execv(compiler, command)
'''
    source = source.replace('Path(SDK)', 'Path(' + repr(str(sdk)) + ')')
    source = source.replace('tools = TOOLS', 'tools = ' + repr(tools))
    path.write_text(source)
    path.chmod(0o755)


def build(args):
    sdk = args.sdk_build.resolve(strict=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'output must be a new directory')
    output = args.output.resolve()
    require(not output.is_relative_to(sdk), 'output must be outside the input SDK')
    metadata = json.loads((sdk / 'manifest.json').read_bytes())
    binding = inspect_sdk('glibc', sdk, features=FEATURES)['binding']
    require(metadata['status'] == 'static_sdk_built' and 'cxx_runtime' not in metadata,
            'input must be an authenticated, uncomposed static C SDK')
    require(not (sdk / 'sysroot/usr/lib/libgcc_eh.a').exists(),
            'separate libgcc_eh needs a distinct qualified unwinder profile')
    pthread_header = sdk / 'sysroot/usr/include/pthread.h'
    declarations = re.findall(r'^extern pthread_t pthread_self[^;]+;', pthread_header.read_text(), re.M)
    require(len(declarations) == 1 and 'const' not in declarations[0], 'unsafe pthread_self declaration')
    names = ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib', 'nm', 'objdump', 'strip', 'readelf')
    tools = {name: tool_identity('x86_64-elf-' + name) for name in names}
    for name, tool in tools.items():
        require(tool.get('available'), 'missing target tool: ' + name)
        if name != 'strip':
            require(tool['sha256'] == metadata['tools']['x86_64-elf-' + name]['sha256'],
                    'target tool differs from C SDK: ' + name)
    lock, locks = read_lock()
    archive_data = read_archive(args.archive, lock['archive_bytes'])
    own_inputs = {str(path.relative_to(ROOT)): sha(path) for path in (
        Path(__file__), ROOT / 'scripts/verify_gcc_shared_source.py',
        ROOT / 'scripts/verify_glibc_source.py', ROOT / 'scripts/xypm_sdk_profile.py',
        ROOT / 'scripts/archive_member_map.py', ROOT / 'scripts/glibc_g1_probe.py',
        ROOT / 'scripts/glibc_g1_deps.py', ROOT / 'scripts/xos_app.py', ROOT / 'scripts/xypm_format.py',
        ROOT / 'src/ports/gcc/source_lock.json', ROOT / 'src/ports/gcc/shared_source_auth.json',
        RECIPE / 'build_glibc_cxx.sh', RECIPE / 'build_unwinder.sh', ROOT / 'LICENSE', ROOT / 'NOTICE')}
    output.mkdir(parents=True)
    env, removed = clean_build_environment(os.environ)
    env.update(LC_ALL='C', CONFIG_SITE='/dev/null')
    for name in tuple(env):
        if name.startswith(('ac_cv_', 'gcc_cv_', 'glibcxx_cv_')):
            del env[name]
            removed.append(name)
    report = {'status': 'building', 'builder_inputs': own_inputs, 'c_sdk_binding': binding,
              'source_locks': locks, 'tools': tools, 'sanitized_environment': sorted(removed),
              'steps': [], 'guest_qualification': 'not_run'}
    work = output / 'work'
    work.mkdir()

    def save():
        write_json(output / 'build_record.json', report)

    def run(name, command, cwd=work, environment=env):
        command = list(map(str, command))
        log = output / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        report['steps'].append({'name': name, 'argv': command, 'returncode': result.returncode,
                                'log_sha256': sha(log)})
        save()
        require(result.returncode == 0, name + ' failed; see ' + str(log))
        return log.read_text(errors='strict')

    try:
        authentication = verify_source(args.archive, args.signature, args.keyring,
                                       output / 'gcc_authentication', archive_data=archive_data)
        report['gcc_authentication'] = authentication
        save()
        extract_verified_source(archive_data, authentication, work)
        del archive_data
        source = work / ('gcc-' + lock['version'])
        configure_source(source)
        triplet = run('build-triplet', ['sh', source / 'config.guess']).strip()
        require(run('target-triplet', ['sh', source / 'config.sub', TARGET]).strip() == TARGET,
                'native target not recognized')
        directories = {name: work / name for name in ('tools', 'std', 'libgcc', 'unwind')}
        for directory in directories.values():
            directory.mkdir()
        tool_dir, std, unwind = (directories[n] for n in ('tools', 'std', 'unwind'))
        shutil.copyfile(source / 'libgcc/gthr-posix.h', directories['libgcc'] / 'gthr-default.h')
        for name in ('as', 'ld'):
            (tool_dir / name).symlink_to(tools[name]['path'])
        write_driver(tool_dir / 'driver', sdk / 'sysroot', tools)
        for name in ('ccc', 'cxx'):
            (tool_dir / name).symlink_to('driver')
        env.update(CC=str(tool_dir / 'ccc'), CXX=str(tool_dir / 'cxx'),
                   CFLAGS='-O2 -g0 -fno-pic', CXXFLAGS='-O2 -g0 -fno-pic', gcc_cv_target_thread_file='posix')
        for name in ('ar', 'ranlib', 'ld', 'nm', 'objdump', 'strip'):
            env[name.upper()] = tools[name]['path']
        make = select_gnu_make()['path']
        probe = std / 'xos_link_test.c'
        probe.write_text('int main(void) { return 0; }\n')
        run('configure-link-probe', [env['CC'], probe, '-o', std / 'xos_link_test'])
        run('cxx-configure', [source / 'libstdc++-v3/configure', '--build=' + triplet,
            '--host=' + TARGET, '--prefix=/usr', '--with-gxx-include-dir=/usr/include/c++/' + lock['version'],
            '--disable-multilib', '--disable-shared', '--disable-nls', '--disable-libstdcxx-pch',
            '--enable-libstdcxx-threads=yes', '--enable-clocale=generic',
            '--disable-libstdcxx-backtrace', '--disable-libstdcxx-filesystem-ts'], std)
        require(re.search(r'^#define _GLIBCXX_HAS_GTHREADS 1$', (std / 'config.h').read_text(), re.M),
                'POSIX target gthreads not active')
        run('cxx-make', [make, '-j' + str(args.jobs)], std)
        export = work / 'cxx-export'
        run('cxx-install', [make, '-j1', 'install', 'DESTDIR=' + str(export)], std)
        run('unwinder-configure', [source / 'libgcc/configure', '--build=' + triplet,
            '--host=x86_64-elf', '--disable-shared', '--disable-gcov'], unwind)
        plugin = Path(run('compiler-plugin', [tools['gcc']['path'], '-print-file-name=plugin']).strip()) / 'include'
        require(plugin.is_dir(), 'matching GCC plugin headers unavailable')
        (unwind / 'tconfig.h').write_text('#define USED_FOR_TARGET 1\n')
        (unwind / 'libgcc_tm.h').write_text('/* 64-bit ELF needs no extra libgcc target header. */\n')
        for target, origin in (('unwind.h', 'unwind-generic.h'), ('md-unwind-support.h', 'config/no-unwind.h'),
                               ('md-unwind-def.h', 'config/no-unwind.h'), ('gthr-default.h', 'gthr-posix.h')):
            shutil.copyfile(source / 'libgcc' / origin, unwind / target)
        flags = ['-B' + str(tool_dir) + '/', '-O2', '-g0', '-fexceptions', '-fbuilding-libgcc',
                 '-fno-stack-protector', '-mno-red-zone', '-fno-pie', '-fno-pic', '-DIN_GCC', '-DIN_LIBGCC2',
                 '-DHAVE_CC_TLS', '-DHAVE_GAS_HIDDEN', '-DGTHREAD_USE_WEAK=0', '-nostdinc',
                 '-I' + str(unwind), '-I' + str(plugin), '-I' + str(source / 'libgcc'), '-I' + str(source / 'include'),
                 '-isystem', str(sdk / 'sysroot/usr/include'), '-isystem', str(sdk / 'sysroot/usr/lib/compiler-include')]
        objects = [unwind / name for name in sorted(GLIBC_UNWINDER_MEMBERS)]
        for obj in objects:
            run('unwinder-' + obj.stem, [tools['gcc']['path'], *flags, '-MD', '-MF', obj.with_suffix('.d'),
                                       '-c', source / 'libgcc' / (obj.stem + '.c'), '-o', obj], unwind)
        sysroot = output / 'sysroot'
        shutil.copytree(sdk / 'sysroot', sysroot, symlinks=True)
        shutil.copytree(sdk / 'source_verification', output / 'source_verification',
                        ignore=shutil.ignore_patterns('gnupg'))
        shutil.copytree(export / 'usr/include/c++', sysroot / 'usr/include/c++', symlinks=True)
        for name in ('libstdc++.a', 'libsupc++.a'):
            shutil.copyfile(export / 'usr/lib' / name, sysroot / 'usr/lib' / name)
        libgcc = sysroot / 'usr/lib/libgcc.a'
        original = archive_members(libgcc)
        require(GLIBC_UNWINDER_MEMBERS <= original.keys(), 'base libgcc lacks qualified replacement members')
        run('compose-unwinder', [tools['ar']['path'], 'rcsD', libgcc, *objects])
        composed = archive_members(libgcc)
        require(composed.keys() == original.keys() and
                all(composed[n] == original[n] for n in original.keys() - GLIBC_UNWINDER_MEMBERS) and
                all(composed[p.name] == p.read_bytes() for p in objects), 'libgcc composition changed other members')
        require(GLIBC_UNWINDER_SYMBOLS <= (strong_undefined_symbols(composed['unwind-dw2-fde.o']) |
                                          strong_undefined_symbols(composed['unwind-dw2.o'])),
                'unwinder lacks strong POSIX frame-registry synchronization')
        materials = sysroot / 'usr/share/xos-glibc/cxx'
        (materials / 'port/keys').mkdir(parents=True)
        (materials / 'licenses').mkdir()
        for name, expected in own_inputs.items():
            target = materials / 'recipe' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
            require(sha(target) == expected, 'recipe source changed while staging: ' + name)
        trust = {name: lock[name] for name in ('primary_fingerprint', 'signing_fingerprint')}
        trust.update(key_file='keys/release_key.gpg', key_sha256=authentication['keyring_sha256'],
                     signature_file='gcc-' + lock['version'] + '.tar.xz.sig')
        source_lock = {'version': lock['version'], 'source_archive': 'gcc-' + lock['version'] + '.tar.xz',
                       'sha256': authentication['archive_sha256'], 'signature_sha256': authentication['signature_sha256'],
                       'signer_trust': trust, 'upstream_source_locks': locks}
        write_json(materials / 'port/source_lock.json', source_lock)
        for src, name, expected in ((args.signature, trust['signature_file'], authentication['signature_sha256']),
                                     (args.keyring, trust['key_file'], authentication['keyring_sha256'])):
            shutil.copyfile(src, materials / 'port' / name)
            require(sha(materials / 'port' / name) == expected, 'authentication material changed')
        for name in ('COPYING3', 'COPYING.RUNTIME'):
            shutil.copyfile(source / name, materials / 'licenses' / name)
        verification = output / 'gcc_source_verification'
        verification.mkdir()
        for name in ('gpgv.status', 'gpgv.log'):
            shutil.copyfile(output / 'gcc_authentication' / name, verification / name)
        shutil.copyfile(materials / 'port' / trust['key_file'], verification / 'release_key.gpg')
        signature = check_status(authentication['gpgv_exit'], (verification / 'gpgv.status').read_text(), trust)
        verified = {'schema': 1, 'status': 'upstream_signature_verified', 'gpgv_exit': authentication['gpgv_exit'],
                    'verified_at': authentication['verified_at'], 'archive_sha256': authentication['archive_sha256'],
                    'signature_sha256': authentication['signature_sha256'], 'key_sha256': authentication['keyring_sha256'],
                    'lock_sha256': sha(materials / 'port/source_lock.json'), 'signature': signature, 'trust_record': trust,
                    'authentication_report_sha256': sha(output / 'gcc_authentication/report.json'),
                    'evidence': {n: sha(verification / n) for n in ('gpgv.status', 'gpgv.log', 'release_key.gpg')}}
        write_json(verification / 'report.json', verified)
        include = 'usr/include/c++/' + lock['version']
        config = sysroot / include / TARGET / 'bits/c++config.h'
        macros = {k: v.strip() for k, v in re.findall(
            r'^[ \t]*#[ \t]*define[ \t]+(_GLIBCXX_[A-Z0-9_]+)[ \t]+([^\n]+)$', config.read_text(), re.M)}
        abi = {k: macros[k] for k in ('_GLIBCXX_USE_CXX11_ABI', '_GLIBCXX_USE_DUAL_ABI',
                                     '_GLIBCXX_INLINE_VERSION', '_GLIBCXX_HAS_GTHREADS')}
        require(abi == dict(zip(abi, ('1', '1', '0', '1'))), 'static C++ ABI differs from qualified profile')
        require(inspect_sdk('glibc', sdk, features=FEATURES)['binding'] == binding, 'input SDK changed during build')
        require(all(sha(ROOT / n) == digest for n, digest in own_inputs.items()), 'builder input changed during build')
        require(all(sha(Path(tool['path'])) == tool['sha256'] for tool in tools.values()), 'target tool changed')
        _, artifacts = sdk_snapshot(sysroot)
        result = {**metadata, 'artifacts': artifacts, 'cxx_source_verification': verified,
                  'cxx_source_verification_report_sha256': sha(verification / 'report.json'),
                  'cxx_runtime': {'status': 'built', 'gcc_version': lock['version'],
                      'source_sha256': authentication['archive_sha256'], 'target': TARGET,
                      'thread_model': 'posix', 'locale_model': 'generic',
                      'include_directories': [include, include + '/' + TARGET, include + '/backward'],
                      'unwinder': {'thread_model': 'posix', 'frame_registry': 'pthread_mutex',
                                  'replaced_members': {p.name: sha(p) for p in objects}}},
                  'cxx_runtime_closure': {'c_sdk_binding': binding, 'builder_inputs': own_inputs,
                      'configure_driver_sha256': sha(tool_dir / 'driver'), 'pthread_header_sha256': sha(pthread_header),
                      'configure_link_probe_sha256': sha(std / 'xos_link_test'), 'public_cxx_abi_macros': abi,
                      'configure_sha256': sha(std / 'config.h'),
                      'unwinder_configure_sha256': sha(unwind / 'auto-target.h'),
                      'unmodified_base_libgcc_members': len(original) - len(objects),
                      'unwinder_dependency_receipts': {p.name: sha(p.with_suffix('.d')) for p in objects}}}
        write_json(output / 'manifest.json', result)
        report['sdk_binding'] = inspect_sdk('glibc', output, cxx=True, features=FEATURES)['binding']
        report['sdk_manifest_sha256'] = sha(output / 'manifest.json')
        report['status'] = 'static_cxx_sdk_built'
        save()
        return report
    except BaseException as error:
        report['status'], report['error'] = 'failed', str(error)
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('archive', 'signature', 'keyring', 'sdk-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=2)
    try:
        result = build(parser.parse_args())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, 'static C++ SDK: ' + str(error) + '\n')
    print(json.dumps({'status': result['status'], 'sdk_manifest_sha256': result['sdk_manifest_sha256']}))


if __name__ == '__main__':
    main()
