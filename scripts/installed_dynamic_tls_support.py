#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pinned PIC TLS inputs and disposable certificate fixtures for installed K4."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import tarfile

from dynamic_artifacts import digest
from glibc_g1_probe import tool_identity
from package_tls_trust_store import compile_snapshot

repository_root = Path(__file__).resolve().parents[1]
tls_port = repository_root / 'src/ports/native_tls'


def prepare_certificates(output):
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    openssl = shutil.which('openssl')
    if not openssl:
        raise ValueError('OpenSSL is required for disposable test certificates')

    def run(*args):
        return subprocess.check_output([openssl, *map(str, args)], cwd=output, stderr=subprocess.PIPE)

    pins = '// Generated disposable test pins; private keys are never installed.\n#include "trust_store.hpp"\n'
    for number in (1, 2):
        root, leaf = f'root-{number}', f'leaf-{number}'
        run('req', '-x509', '-newkey', 'rsa:2048', '-noenc', '-sha256', '-days', '7',
            '-subj', f'/CN=XOS installed K4 root {number}', '-keyout', root + '.key',
            '-out', root + '.pem', '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign')
        run('req', '-new', '-newkey', 'rsa:2048', '-noenc', '-sha256',
            '-subj', '/CN=tls.xos.test', '-keyout', leaf + '.key', '-out', leaf + '.csr')
        (output / 'extensions.cnf').write_text('basicConstraints=critical,CA:FALSE\n'
            'keyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n'
            'subjectAltName=DNS:tls.xos.test\n')
        run('x509', '-req', '-in', leaf + '.csr', '-sha256', '-CA', root + '.pem',
            '-CAkey', root + '.key', '-set_serial', secrets.randbits(127) or 1, '-days', '4',
            '-extfile', 'extensions.cnf', '-out', leaf + '.pem')
        run('verify', '-CAfile', root + '.pem', '-verify_hostname', 'tls.xos.test', leaf + '.pem')
        snapshot = compile_snapshot((output / (root + '.pem')).read_bytes(), number)[0]
        (output / f'roots-{number}.bin').write_bytes(snapshot)
        pin = ', '.join(f'0x{value:02x}' for value in hashlib.sha256(snapshot).digest())
        pins += f'static const native_tls::trust_store_pin installed_tls_pin_{number}' + '{' + f'{number}, ' + '{' + pin + '}};\n'
    (output / 'installed_tls_pins.hpp').write_text(pins)
    receipt = {'status': 'disposable_test_fixtures',
               'generator': run('version').decode().strip(),
               'public_files': {path.name: digest(path) for path in sorted(output.iterdir())
                                if path.suffix in ('.pem', '.bin', '.hpp')}}
    (output / 'certificates.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def build_support(archive, certificates, output, sysroot, native, tools, run, inputs, report):
    """Build TLS against this GNU sysroot and this native SDK, without any libc archive."""
    lock_path = tls_port / 'source_lock.json'
    lock = json.loads(lock_path.read_bytes())
    if digest(archive) != lock['archive_sha256']:
        raise ValueError('Mbed TLS archive differs from the existing upstream source lock')
    source = output / 'tls_source'
    source.mkdir()
    with tarfile.open(archive, 'r:bz2') as package:
        package.extractall(source, filter='data')
    upstream = source / lock['source_root']
    for name, expected in lock['notices'].items():
        if digest(upstream / name) != expected:
            raise ValueError('upstream notice changed: ' + name)
        target = output / 'notices' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(upstream / name, target)
    configs = {'MBEDTLS_USER_CONFIG_FILE': tls_port / 'mbedtls_xos_config.h',
               'TF_PSA_CRYPTO_USER_CONFIG_FILE': tls_port / 'tf_psa_crypto_xos_config.h'}
    sources = [tls_port / 'platform.c', tls_port / 'stream.cpp', tls_port / 'trust_store.cpp',
               repository_root / 'src/user/arch/x86_64/syscall.cpp']
    for path in [Path(__file__), lock_path, *sources, *configs.values(),
                 tls_port / 'stream.hpp', tls_port / 'trust_store.hpp', certificates / 'installed_tls_pins.hpp',
                 certificates / 'certificates.json', archive]:
        inputs[str(path)] = digest(path)
    cflags = ['--sysroot=' + str(sysroot), '-nostdinc', '-isystem', str(sysroot / 'usr/include'),
              '-isystem', str(sysroot / 'usr/lib/compiler-include'), '-D_GNU_SOURCE', '-mno-red-zone',
              '-fPIC', '-fno-builtin', '-ffunction-sections', '-fdata-sections', '-ftls-model=initial-exec']
    options = {'CMAKE_SYSTEM_NAME': 'Generic', 'CMAKE_SYSTEM_PROCESSOR': 'x86_64',
               'CMAKE_TRY_COMPILE_TARGET_TYPE': 'STATIC_LIBRARY', 'CMAKE_BUILD_TYPE': 'Release',
               'CMAKE_C_COMPILER': tools['gcc']['path'], 'CMAKE_AR': tools['ar']['path'],
               'CMAKE_RANLIB': tools['ranlib']['path'], 'CMAKE_C_FLAGS': shlex.join(cflags),
               'ENABLE_PROGRAMS': 'OFF', 'ENABLE_TESTING': 'OFF', 'GEN_FILES': 'OFF',
               'DISABLE_PACKAGE_CONFIG_AND_INSTALL': 'ON', **configs}
    build = output / 'tls_build'
    cmake = tool_identity('cmake')
    if not cmake.get('available'):
        raise ValueError('CMake is required')
    run('tls-configure', [cmake['path'], '-S', upstream, '-B', build,
                          *(f'-D{name}={value}' for name, value in options.items())])
    run('tls-libraries', [cmake['path'], '--build', build, '--parallel', '2', '--target', 'mbedtls'])
    # The ordinary native SDK also ships its separate historical C headers.
    # Export only xos/ here so those cannot shadow this GNU sysroot's cdefs,
    # stdio, pthread or errno definitions through GCC's -I search precedence.
    native_headers = output / 'native_headers'
    native_headers.mkdir()
    shutil.copytree(native / 'include/xos', native_headers / 'xos')
    includes = [tls_port, certificates, upstream / 'include', upstream / 'tf-psa-crypto/include',
                upstream / 'tf-psa-crypto/drivers/builtin/include', native_headers]
    headers = [*(f'-D{name}="{path}"' for name, path in configs.items()), *(f'-I{path}' for path in includes)]
    objects = []
    cxx_flags = ['-std=gnu++20', '-nostdinc++', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics',
                 '-fno-use-cxa-atexit']
    for path in sources:
        target = output / ('tls_' + path.stem + '.o')
        is_c = path.suffix == '.c'
        run('tls-' + path.stem, [tools['gcc' if is_c else 'g++']['path'], *cflags,
            *(['-std=gnu11'] if is_c else cxx_flags), '-O2', '-Wall', '-Wextra', '-Werror',
            *headers, '-c', path, '-o', target])
        objects.append(target)
    libraries = [build / 'library/libmbedtls.a', build / 'library/libmbedx509.a',
                 build / 'tf-psa-crypto/core/libtfpsacrypto.a']
    report['tls'] = {'source_lock_sha256': digest(lock_path), 'archive_sha256': digest(archive),
        'cmake': cmake, 'model': 'PIC_static_TLS_code_in_GNU_dynamic_PIE', 'libc_archive_linked': False,
        'native_headers': 'xos_namespace_only; all C headers from the pinned GNU sysroot',
        'artifacts': {str(path.relative_to(output)): digest(path) for path in objects + libraries},
        'certificate_fixtures': json.loads((certificates / 'certificates.json').read_bytes())}
    return cxx_flags + headers, objects + ['--start-group', *libraries, '--end-group']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--certificates', type=Path, required=True)
    prepare_certificates(parser.parse_args().certificates.absolute())
