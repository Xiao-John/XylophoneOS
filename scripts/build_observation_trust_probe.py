#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build/run real loaded-trust bridge checks, optionally for a signed XOS glibc SDK.

Only Mbed TLS archives are reused from an explicitly supplied, hash-verified
build. The bridge, parser adapter, platform and disposable CA fixtures are new.
No earlier guest result or TLS/network qualification is inherited.
"""
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
import tempfile

from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from package_tls_trust_store import compile_snapshot
from xypm_sdk_profile import source_binding

ROOT = Path(__file__).resolve().parents[1]
TLS = ROOT / 'src/ports/native_tls'
SOURCE_NAMES = (
    'tests/fixtures/observation_trust_probe.cpp',
    'src/ports/native_tls/trust_store.cpp', 'src/ports/native_tls/trust_store.hpp',
    'src/ports/native_tls/observation.hpp', 'src/ports/native_tls/platform.c',
    'src/ports/native_tls/mbedtls_xos_config.h', 'src/ports/native_tls/tf_psa_crypto_xos_config.h',
    'src/ports/native_tls/source_lock.json', 'src/user/include/xos/observation_sources.hpp',
    'src/user/include/xos/observation.hpp', 'src/shared/include/xos/observation_service_abi.hpp',
    'scripts/build_observation_trust_probe.py', 'scripts/package_tls_trust_store.py',
    'scripts/build_glibc_program.py', 'scripts/glibc_g1_probe.py', 'scripts/xypm_sdk_profile.py',
    'src/user/observation/sources.cpp', 'src/user/observation/json.cpp',
    'src/user/observation/endpoint.cpp', 'src/user/loader/dynamic/generation.cpp',
    'src/user/sdk/text.cpp', 'src/user/arch/x86_64/syscall.cpp',
)
ARCHIVES = ('mbedtls/library/libmbedx509.a', 'mbedtls/tf-psa-crypto/core/libtfpsacrypto.a')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'tls-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--sdk', type=Path, help='completed signed-source static glibc SDK build; omit for host')
    args = parser.parse_args()
    archive, previous = args.archive.resolve(strict=True), args.tls_build.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True) if args.sdk else None
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    sources = {name: sha(ROOT / name) for name in SOURCE_NAMES}
    report = {'status': 'failed', 'profile': 'loaded_trust_snapshot', 'target': 'glibc' if sdk else 'host',
              'sources': sources, 'commands': [], 'guest': 'not_run', 'tls_handshake': 'not_run',
              'network_traffic': 'not_run', 'reused_build_receipt_sha256': sha(previous / 'receipt.json')}
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    report['sanitized_environment'] = removed

    def run(name, command):
        command = [str(value) for value in command]
        report['commands'].append(command)
        with (out / (name + '.log')).open('w') as log:
            log.write(shlex.join(command) + '\n'); log.flush()
            subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)

    try:
        lock = json.loads((TLS / 'source_lock.json').read_bytes())
        old = json.loads((previous / 'receipt.json').read_bytes())
        if sha(archive) != lock['archive_sha256'] or old['archive_sha256'] != lock['archive_sha256'] or old['status'] != 'linked':
            raise ValueError('Mbed TLS source/build identity differs')
        for name in ('platform.c', 'mbedtls_xos_config.h', 'tf_psa_crypto_xos_config.h'):
            relative = 'src/ports/native_tls/' + name
            if sources[relative] != old['inputs'][relative]:
                raise ValueError('reused Mbed TLS configuration differs: ' + name)
        archives = [previous / name for name in ARCHIVES]
        archive_hashes = {name: sha(previous / name) for name in ARCHIVES}
        if any(archive_hashes[name] != old['archives'][name] for name in ARCHIVES):
            raise ValueError('reused Mbed TLS archive differs')
        report.update(archive_sha256=lock['archive_sha256'], reused_archives=archive_hashes)
        extracted = out / 'source'; extracted.mkdir()
        with tarfile.open(archive, 'r:bz2') as bundle:
            bundle.extractall(extracted, filter='data')
        upstream = extracted / lock['source_root']
        for name, digest in lock['notices'].items():
            if sha(upstream / name) != digest: raise ValueError('upstream notice differs')
            destination = out / 'notices' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(upstream / name, destination)

        header = '#include "trust_store.hpp"\n'
        fixture_pins = {}
        with tempfile.TemporaryDirectory(prefix='xos_observation_ca_') as temporary:
            for generation in (7, 8):
                key, pem = Path(temporary) / 'root.key', Path(temporary) / 'root.pem'
                run('ca-' + str(generation), ['openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt',
                    'ec_paramgen_curve:P-256', '-noenc', '-sha256', '-days', '1', '-subj',
                    '/CN=XOS disposable observation root ' + str(generation), '-addext',
                    'basicConstraints=critical,CA:TRUE', '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
                    '-keyout', key, '-out', pem])
                data, _ = compile_snapshot(pem.read_bytes(), generation)
                digest = hashlib.sha256(data).digest()
                fixture_pins[str(generation)] = digest.hex()
                header += 'static const unsigned char trust_data_' + str(generation) + '[]={' + ','.join(map(str, data)) + '};\n'
                header += 'static const native_tls::trust_store_pin trust_pin_' + str(generation) + '{' + str(generation) + ',{' + ','.join(map(str, digest)) + '}};\n'
                (out / ('trust-' + str(generation) + '.bin')).write_bytes(data)
        (out / 'observation_trust_data.hpp').write_text(header)
        report['fixture_pins'] = fixture_pins
        includes = [TLS, out, upstream / 'include', upstream / 'tf-psa-crypto/include',
                    upstream / 'tf-psa-crypto/drivers/builtin/include', ROOT / 'src/user/include', ROOT / 'src/shared/include']
        flags = ['-O2', '-Wall', '-Wextra', '-Werror', '-fno-pie', '-ffunction-sections', '-fdata-sections']
        for name, path in {'MBEDTLS_USER_CONFIG_FILE': TLS / 'mbedtls_xos_config.h',
                           'TF_PSA_CRYPTO_USER_CONFIG_FILE': TLS / 'tf_psa_crypto_xos_config.h'}.items():
            flags.append(f'-D{name}="{path}"')
        flags += ['-I' + str(path) for path in includes]
        if sdk:
            manifest = json.loads((sdk / 'manifest.json').read_bytes())
            if manifest['status'] != 'static_sdk_built': raise ValueError('completed signed glibc SDK required')
            sysroot = sdk / 'sysroot'
            authentication, _ = source_binding(sdk, sysroot, manifest)
            if authentication['archive_sha256'] != manifest['source_sha256']: raise ValueError('glibc source differs')
            for name, digest in manifest['artifacts'].items():
                if sha(sysroot / name) != digest: raise ValueError('glibc artifact differs: ' + name)
            for name in ('clock_gettime.c', 'getrandom.c'):
                relative = 'src/ports/glibc/sysdeps/xos/' + name
                if sha(ROOT / relative) != manifest['inputs'][relative]: raise ValueError('glibc platform differs')
            tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'as', 'ld')}
            for name, item in tools.items():
                if item['sha256'] != manifest['tools']['x86_64-elf-' + name]['sha256']:
                    raise ValueError('glibc tool differs: ' + name)
            tool_dir = out / 'tools'; tool_dir.mkdir()
            for name in ('as', 'ld'): (tool_dir / name).symlink_to(tools[name]['path'])
            flags += [f'--sysroot={sysroot}', f'-B{tool_dir}/', '-nostdinc', '-isystem', str(sysroot / 'usr/include'),
                      '-isystem', str(sysroot / 'usr/lib/compiler-include'), '-D_GNU_SOURCE', '-mno-red-zone',
                      '-fno-builtin', '-ftls-model=local-exec']
            report.update(sdk_manifest_sha256=sha(sdk / 'manifest.json'), glibc_source_sha256=manifest['source_sha256'],
                          glibc_verification_sha256=authentication['report_sha256'])
        else:
            tools = {name: tool_identity(name) for name in ('gcc', 'g++')}
        report['tools'] = tools
        objects = []
        compile_sources = [TLS / 'platform.c', TLS / 'trust_store.cpp', ROOT / SOURCE_NAMES[0]]
        if sdk:
            flags += ['-DXOS_OBSERVATION_TRUST_GUEST=1']
            compile_sources += [ROOT / name for name in SOURCE_NAMES[-6:]]
        for source in compile_sources:
            obj = out / (source.stem + '.o')
            use_c = source.suffix == '.c'
            language = ['-std=gnu11'] if use_c else ['-std=gnu++20', '-fno-exceptions', '-fno-rtti', '-nostdinc++']
            run(source.stem, [tools['gcc' if use_c else 'g++']['path'], *flags, *language, '-c', source, '-o', obj])
            objects.append(obj)
        elf = out / ('observation_trust.elf' if sdk else 'observation_trust_host')
        if sdk:
            lib = sysroot / 'usr/lib'
            run('link', [tools['gcc']['path'], f'--sysroot={sysroot}', f'-B{tool_dir}/', '-static', '-no-pie', '-nostdlib',
                '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T', sysroot / 'user.ld', '-o', elf,
                *(lib / name for name in ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')), *objects,
                '-Wl,--start-group', *archives, *(lib / name for name in ('libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a')),
                '-Wl,--end-group', lib / 'crtend.o', lib / 'crtn.o'])
            report['program_headers'] = verify_elf(elf)
            report['status'] = 'built_not_run'
        else:
            run('link', [tools['g++']['path'], '-no-pie', '-Wl,--gc-sections', *objects, '-Wl,--start-group',
                         *archives, '-Wl,--end-group', '-o', elf])
            run('checks', [elf])
            result = (out / 'checks.log').read_text()
            checks = re.findall(r'^OBS_TRUST_CHECK (\S+) PASS$', result, re.M)
            if len(checks) != 14 or 'OBS_TRUST_PASS checks=14' not in result or ' FAIL' in result:
                raise ValueError('incomplete loaded trust checks')
            report.update(status='passed', checks=checks)
        if sources != {name: sha(ROOT / name) for name in SOURCE_NAMES} or any(sha(previous / name) != value for name, value in archive_hashes.items()):
            raise ValueError('build inputs changed')
        report['artifacts'] = {elf.name: sha(elf), 'observation_trust_data.hpp': sha(out / 'observation_trust_data.hpp'),
                               **{f'trust-{gen}.bin': sha(out / f'trust-{gen}.bin') for gen in (7, 8)}}
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS loaded trust', report['target'], report['status'])


if __name__ == '__main__':
    main()
