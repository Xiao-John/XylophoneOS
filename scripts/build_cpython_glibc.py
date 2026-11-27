# SPDX-License-Identifier: Apache-2.0
"""Build the static CPython core for an explicitly selected XOS glibc profile."""

import argparse
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from build_cpython_legacy import (
    DEFAULT_ARCHIVE, PORT, apply_patches, ensure_build_python, extract_source, hash_tree,
    write_setup_local,
)
from build_cpython_zlib import glibc_zlib_binding
from build_openssl_target import BUILDER as OPENSSL_BUILDER, LOCK as OPENSSL_LOCK
from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from xypm_format import canonical, inspect_elf, load_json, require, sha_file
from xypm_sdk_profile import metadata_snapshot, relative_file, verify_profile

TOOL_NAMES = ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib', 'readelf')
LEGACY_ONLY_PROBES = {
    'ac_cv_header_sys_resource_h', 'ac_cv_header_sched_h',
    'ac_cv_func_clock', 'ac_cv_func_times',
}
SOCKET_HEADERS = ('arpa/inet.h', 'netdb.h', 'netinet/tcp.h')
SOCKET_FUNCTIONS = {'accept', 'bind', 'connect', 'listen', 'socket'}
UNQUALIFIED = [
    'dynamic extension loading', 'Pillow', 'zlib', 'SQLite', 'bzip2/xz/zstd',
    'full standard library', 'interactive REPL',
]


def build_environment():
    env, removed = clean_build_environment(os.environ)
    selectors = {'LIBS', 'LDSHARED', 'MODLIBS', 'DYNLOADFILE', 'MODULE_BUILDTYPE',
                 'PYTHONPATH', 'PYTHONHOME', 'PYTHON_FOR_BUILD', 'PYTHON_FOR_BUILD_DEPS',
                 '_PYTHON_HOST_PLATFORM', '_PYTHON_SYSCONFIGDATA_NAME', 'PKG_CONFIG'}
    for name in sorted(env):
        if (name in selectors or name.startswith(('ac_cv_', 'py_cv_'))
                or name.endswith(('_CFLAGS', '_CPPFLAGS', '_LDFLAGS', '_LIBS'))):
            del env[name]
            removed.append(name)
    env.update(LC_ALL='C', PKG_CONFIG_PATH='', PKG_CONFIG_LIBDIR=os.devnull)
    return env, sorted(removed)


def target_site(path, stub_functions, socket_available):
    values = {}
    for line in (PORT / 'config/xos_config.site').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, value = line.split('=', 1)
        if name not in LEGACY_ONLY_PROBES:
            values[name] = value
    for name in stub_functions:
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name), 'invalid SDK stub name')
        values['ac_cv_func_' + name] = 'no'
    values.update(ac_cv_func_dlopen='no', ac_cv_lib_dl_dlopen='no')
    if not socket_available:
        # CPython's module probe omits required headers and accepts stub symbols.
        # Its n/a override skips that probe without hiding SDK headers from other modules.
        values['py_cv_module__socket'] = 'n/a'
    path.write_text(''.join(name + '=' + value + '\n' for name, value in sorted(values.items())))


def glibc_openssl_binding(build, sdk_binding, sdk_digest, profile_digest):
    receipt, receipt_digest = metadata_snapshot(build / 'report.json')
    lock, lock_digest = metadata_snapshot(OPENSSL_LOCK)
    require(receipt['status'] == 'static_sdk_and_probe_linked'
            and receipt['builder_sha256'] == sha_file(OPENSSL_BUILDER)
            and receipt['source_lock_sha256'] == lock_digest
            and receipt['source']['status'] == 'upstream_signature_verified'
            and receipt['source']['archive_sha256'] == lock['archive_sha256']
            and receipt['sdk_binding'] == sdk_binding and receipt['sdk_manifest_sha256'] == sdk_digest
            and receipt['sdk_profile_sha256'] == profile_digest
            and 'no-sock' in receipt['configure'], 'OpenSSL build differs from the bound static SDK')
    prefix = build / 'prefix'
    artifacts = receipt['installed']
    required = {'usr/lib/libcrypto.a', 'usr/lib/libssl.a', 'usr/include/openssl/evp.h',
                'usr/include/openssl/configuration.h', 'LICENSE.txt'}
    require(required <= artifacts.keys()
            and artifacts['LICENSE.txt'] == lock['license_sha256'], 'OpenSSL build materials are incomplete')
    for name, digest in artifacts.items():
        require(sha_file(relative_file(prefix, name)) == digest, 'OpenSSL build material changed: ' + name)
    return {'version': lock['version'], 'license_sha256': lock['license_sha256'],
            'build_receipt_sha256': receipt_digest, 'artifacts': artifacts}


def build(args, env, removed):
    archive = args.archive.resolve(strict=True)
    lock = load_json(PORT / 'source_lock.json')
    require(sha_file(archive) == lock['sha256'], 'CPython archive differs from source lock')
    profile_path = args.glibc_profile.resolve(strict=True)
    profile, profile_digest = metadata_snapshot(profile_path)
    binding = verify_profile(profile, 'glibc', args.sdk)
    sdk = args.sdk.resolve(strict=True)
    sysroot = sdk / 'sysroot'
    lib = sysroot / 'usr/lib'
    manifest = sdk / 'manifest.json'
    sdk_digest = profile['sdk_binding']['sdk_manifest_sha256']
    metadata, _ = metadata_snapshot(manifest, sdk_digest)
    stub_functions = set(metadata['stub_functions'])
    required = {'clock_gettime', 'clock_getres', 'pthread_create', 'pthread_join'}
    require(not required & stub_functions, 'SDK lacks native clock or pthread support')
    socket_available = not (SOCKET_FUNCTIONS & stub_functions) and all(
        (sysroot / 'usr/include' / name).is_file() for name in SOCKET_HEADERS)

    tools = {name: tool_identity('x86_64-elf-' + name) for name in TOOL_NAMES}
    for name, tool in tools.items():
        require(tool.get('available') and tool.get('sha256') == metadata['tools']['x86_64-elf-' + name]['sha256'],
                'cross tool differs from the SDK build: ' + name)
    make = select_gnu_make()
    zlib = (glibc_zlib_binding(args.zlib_prefix, binding, sdk_digest, profile_digest)
            if args.zlib_prefix else None)
    openssl = (glibc_openssl_binding(args.openssl_build, binding, sdk_digest, profile_digest)
               if args.openssl_build else None)
    work = args.output_dir.resolve()
    require(not work.is_relative_to(sdk) and not work.is_relative_to(PORT),
            'build directory must be outside the SDK and port inputs')
    work.mkdir(parents=True, exist_ok=False)
    scripts = [Path(__file__), Path(__file__).with_name('build_cpython.py'),
               Path(__file__).with_name('build_cpython_legacy.py')]
    script_hashes = {path.name: sha_file(path) for path in scripts}
    port_hashes = hash_tree(PORT)
    report = {'phase': 'G4', 'version': lock['version'], 'target': lock['target'],
              'runtime_family': 'glibc', 'profile': profile['id'], 'sdk_path': str(sdk),
              'sdk_manifest_sha256': sdk_digest, 'sdk_binding': binding, 'profile_file_sha256': profile_digest,
              'source_archive_sha256': lock['sha256'], 'port_inputs': port_hashes,
              'builder_inputs': script_hashes, 'tools': tools, 'make': make,
              'build_options': {'source_date_epoch': args.source_date_epoch, 'make_jobs': args.make_jobs},
              'sanitized_environment': removed, 'static_extensions': [], 'unqualified': list(UNQUALIFIED),
              'steps': [], 'guest_tested': False, 'status': 'preparing'}
    receipt = work / 'py0a_report.json'
    source = work / 'source'
    target = work / 'target_build'
    target.mkdir()
    tool_dir = work / 'tools'
    tool_dir.mkdir()
    for name, tool in tools.items():
        (tool_dir / name).symlink_to(tool['path'])

    def run(name, argv):
        log = work / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(argv, cwd=target, env=env, stdout=stream, stderr=subprocess.STDOUT)
        report['steps'].append({'name': name, 'argv': argv, 'exit_code': result.returncode,
                                'log_sha256': sha_file(log)})
        require(result.returncode == 0, name + ' failed; see ' + str(log))

    try:
        if zlib:
            staged_zlib = work / 'zlib'
            for relative, digest in zlib['artifacts'].items():
                destination = staged_zlib / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args.zlib_prefix / relative, destination)
                require(sha_file(destination) == digest, 'zlib changed while staging CPython inputs')
            report['zlib'] = zlib
            report['static_extensions'] = ['zlib']
            report['unqualified'] = [item for item in UNQUALIFIED if item != 'zlib']
        if not socket_available:
            report['unqualified'].append('socket')
        if openssl:
            staged_openssl = work / 'openssl'
            for relative, digest in openssl['artifacts'].items():
                destination = staged_openssl / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(relative_file(args.openssl_build / 'prefix', relative), destination)
                require(sha_file(destination) == digest, 'OpenSSL changed while staging CPython inputs')
            report['openssl'] = openssl
            report['static_extensions'].append('_hashlib')
            report['unqualified'] += ['_ssl and socket TLS']
        extract_source(archive, source)
        apply_patches(source)
        setup = write_setup_local(source, None, {})
        version = tuple(int(part) for part in lock['version'].split('.'))
        build_python = ensure_build_python(source, work, version, args.build_python, make_jobs=args.make_jobs)
        build_python_digest = sha_file(build_python)
        host_triplet = subprocess.check_output(['sh', str(source / 'config.guess')],
                                               env=env, text=True).strip()
        target_triplet = subprocess.check_output(['sh', str(source / 'config.sub'), lock['target']],
                                                 env=env, text=True).strip()
        require(target_triplet == lock['target'], 'CPython target is not canonical XOS')
        report.update(host_build_triplet=host_triplet, build_python=str(build_python),
                      build_python_sha256=build_python_digest, setup_local_sha256=sha_file(setup))

        common = ['--sysroot=' + str(sysroot), '-B' + str(tool_dir) + '/',
                  '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector', '-ftls-model=local-exec']
        includes = ['-nostdinc', '-isystem', str(sysroot / 'usr/include'), '-isystem', str(lib / 'compiler-include')]
        native = sysroot / 'usr/share/xos/terminal-support/src'
        bridge = work / 'xos_time.o'
        run('time_bridge', [tools['g++']['path'], *common, *includes, '-nostdinc++', '-ffreestanding',
                            '-fno-exceptions', '-fno-rtti', '-ffunction-sections', '-fdata-sections',
                            '-I' + str(native / 'shared/include'), '-I' + str(native / 'user/include'),
                            '-c', str(PORT / 'xos_time.cpp'), '-o', str(bridge)])
        report['time_bridge_sha256'] = sha_file(bridge)

        start = ['xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o']
        end = ['crtend.o', 'crtn.o']
        archives = ['libc.a', 'libm.a']
        if 'usr/lib/libxos_terminal.a' in profile['sdk_binding']['link_artifacts']:
            archives.append('libxos_terminal.a')
        archives.append('libgcc.a')
        if (lib / 'libgcc_eh.a').is_file():
            archives.append('libgcc_eh.a')
        link_archives = [str(lib / name) for name in archives]
        if openssl:
            # Configure appends -lcrypto after LIBS for its hashlib probe.
            # Put the static archive with its SDK dependencies in the group.
            link_archives.insert(0, str(staged_openssl / 'usr/lib/libcrypto.a'))
        site = work / 'config.site'
        target_site(site, stub_functions, socket_available)
        if openssl:
            # CPython's configure probe is also satisfied without SSL_set_fd,
            # which _ssl requires even when a caller only uses MemoryBIO.
            with site.open('a') as stream:
                stream.write('ac_cv_working_openssl_ssl=no\n')
        target_env = dict(CC=shlex.join([tools['gcc']['path'], *common]),
                          CXX=shlex.join([tools['g++']['path'], *common]),
                          AR=tools['ar']['path'], RANLIB=tools['ranlib']['path'],
                          READELF=tools['readelf']['path'],
                          CFLAGS='-O2 -ffunction-sections -fdata-sections',
                          CPPFLAGS=shlex.join(['-D__xos__=1', *includes]),
                          LDFLAGS='-nostdlib -static -no-pie '
                                  '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
                          LIBS=shlex.join(['-T', str(sysroot / 'user.ld'), *[str(lib / name) for name in start],
                                           str(bridge), '-Wl,--start-group',
                                           *link_archives, '-Wl,--end-group',
                                           *[str(lib / name) for name in end]]),
                          CONFIG_SITE=str(site), PYTHON_FOR_BUILD=str(build_python))
        if zlib:
            target_env.update(ZLIB_CFLAGS=shlex.join(['-I' + str(staged_zlib / 'include')]),
                              ZLIB_LIBS=shlex.join([str(staged_zlib / 'lib/libz.a')]))
        env.update(target_env)
        report['target_environment'] = target_env
        report['config_site_sha256'] = sha_file(site)
        configure = [str(source / 'configure'), '--prefix=/usr', '--build=' + host_triplet,
                     '--host=' + target_triplet, '--with-build-python=' + str(build_python),
                     '--without-ensurepip', '--disable-test-modules', '--without-mimalloc',
                     '--without-readline', '--disable-ipv6']
        if openssl:
            configure += ['--with-openssl=' + str(staged_openssl / 'usr'), '--with-openssl-rpath=no']
        run('target_configure', configure)
        config = (target / 'pyconfig.h').read_text()
        makefile = (target / 'Makefile').read_text().splitlines()
        require('#define HAVE_PTHREAD_STUBS' not in config and '#define HAVE_CLOCK_GETTIME 1' in config
                and '#define HAVE_CLOCK_GETRES 1' in config
                and any(line.startswith('DYNLOADFILE=') and line.split('=', 1)[1].strip() == 'dynload_stub.o'
                        for line in makefile), 'CPython configure did not select native threads and static loading')
        require(('MODULE_ZLIB_STATE=yes' in makefile) == bool(zlib),
                'CPython configure selected an unexpected zlib module state')
        if not socket_available:
            require('MODULE__SOCKET_STATE=n/a' in makefile,
                    'CPython configure enabled socket without the required SDK support')
        if openssl:
            require('MODULE__HASHLIB_STATE=yes' in makefile and 'MODULE__SSL_STATE=missing' in makefile,
                    'CPython configure did not select OpenSSL hashlib alone')
        shutil.copyfile(setup, target / 'Modules/Setup.local')
        run('target_setup', [str(source / 'Modules/makesetup'), '-c', str(source / 'Modules/config.c.in'),
                             '-s', 'Modules', 'Modules/Setup.local', 'Modules/Setup.stdlib',
                             'Modules/Setup.bootstrap', str(source / 'Modules/Setup')])
        os.replace(target / 'config.c', target / 'Modules/config.c')
        report['generated_config_sha256'] = sha_file(target / 'Modules/config.c')
        report['pyconfig_sha256'] = sha_file(target / 'pyconfig.h')
        report['status'] = 'configured_not_built'
        if args.compile_probe:
            run('target_make', [make['path'], f'-j{args.make_jobs}', 'python'])
            python = target / 'python.exe'
            if not python.is_file():
                shutil.copy2(target / 'python', python)
            layout = inspect_elf(python)
            require(layout['static_tls'], 'CPython static ELF is missing native TLS')
            run('elf', [tools['readelf']['path'], '-W', '-h', '-l', str(python)])
            report['executable'] = {'path': str(python), 'bytes': python.stat().st_size,
                                    'sha256': sha_file(python), 'layout': layout}
            report['status'] = 'built_not_run'
        require(sha_file(archive) == lock['sha256'] and hash_tree(PORT) == port_hashes
                and {path.name: sha_file(path) for path in scripts} == script_hashes,
                'CPython source or builder changed during build')
        require(sha_file(profile_path) == profile_digest and verify_profile(profile, 'glibc', sdk) == binding
                and sha_file(manifest) == sdk_digest, 'SDK or profile changed during CPython build')
        if zlib:
            require(glibc_zlib_binding(args.zlib_prefix, binding, sdk_digest, profile_digest) == zlib
                    and all(sha_file(staged_zlib / name) == digest for name, digest in zlib['artifacts'].items()),
                    'zlib inputs changed during CPython build')
        if openssl:
            require(glibc_openssl_binding(args.openssl_build, binding, sdk_digest, profile_digest) == openssl
                    and all(sha_file(staged_openssl / name) == digest
                            for name, digest in openssl['artifacts'].items()),
                    'OpenSSL inputs changed during CPython build')
        require(sha_file(build_python) == build_python_digest
                and all(sha_file(tool['path']) == tool['sha256'] for tool in (*tools.values(), make)),
                'build Python or toolchain changed during CPython build')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        receipt.write_bytes(canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog='External extension inputs (including Pillow) use the legacy route.')
    parser.add_argument('--archive', type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument('--sdk', type=Path, required=True, help='verified glibc SDK build directory')
    parser.add_argument('--glibc-profile', type=Path, required=True, help='static glibc SDK profile JSON')
    parser.add_argument('--output-dir', type=Path, required=True, help='new private work directory')
    parser.add_argument('--build-python', type=Path, help='matching host CPython; built from the source lock if omitted')
    parser.add_argument('--zlib-prefix', type=Path, help='bound zlib prefix from build_cpython_zlib.py --glibc-profile')
    parser.add_argument('--openssl-build', type=Path, help='bound OpenSSL build for static _hashlib')
    parser.add_argument('--compile-probe', action='store_true', help='also compile and link the static interpreter')
    parser.add_argument('--source-date-epoch', type=int, default=os.environ.get('SOURCE_DATE_EPOCH'),
                        help='pin the compiler build timestamp (default: SOURCE_DATE_EPOCH when set)')
    parser.add_argument('--make-jobs', type=int, choices=(1, 2), default=2,
                        help='use one job to preserve the order of the recorded make output')
    args = parser.parse_args()
    if args.source_date_epoch is not None and not 0 <= args.source_date_epoch <= 253402300799:
        parser.error('--source-date-epoch must be a nonnegative Unix timestamp through year 9999')
    inherited = os.environ.copy()
    env, removed = build_environment()
    if args.source_date_epoch is not None:
        env['SOURCE_DATE_EPOCH'] = str(args.source_date_epoch)
    try:
        # Tool discovery and the reused host builder inherit the CLI process environment.
        os.environ.clear()
        os.environ.update(env)
        report = build(args, env, removed)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, 'CPython glibc: ' + str(error) + '\n')
    finally:
        os.environ.clear()
        os.environ.update(inherited)
    summary = {name: report[name] for name in ('status', 'version', 'runtime_family', 'profile',
                                                'sdk_manifest_sha256', 'guest_tested')}
    if 'executable' in report:
        summary['executable'] = report['executable']
    summary['report'] = str(args.output_dir.absolute() / 'py0a_report.json')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
