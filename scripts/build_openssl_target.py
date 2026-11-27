#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a signed, statically linkable OpenSSL prefix for the bound XOS glibc SDK."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from verify_glibc_source import check_status, decode_key, digest, extract_verified_source, read_archive
from xypm_sdk_profile import metadata_snapshot, verify_profile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/openssl'
LOCK = PORT / 'source_lock.json'
PROBE = ROOT / 'tests/fixtures/openssl/native_probe.c'
LIBS = ('libssl.a', 'libcrypto.a')
BUILDER = Path(__file__).resolve()


def release_snapshot(args, lock, output, env):
    source = read_archive(args.archive, lock['archive_bytes'])
    signature, keys = args.signature.read_bytes(), args.release_keys.read_bytes()
    for label, content in (('archive', source), ('signature', signature), ('release_keys', keys)):
        if sha256(content).hexdigest() != lock[label + '_sha256']:
            raise ValueError(f'OpenSSL {label} differs from the source lock')

    security = output / 'verification'
    security.mkdir(mode=0o700)
    begin = b'-----BEGIN PGP PUBLIC KEY BLOCK-----'
    end = b'-----END PGP PUBLIC KEY BLOCK-----'
    key = security / 'release.gpg'
    key.write_bytes(decode_key(args.release_keys, data=keys[keys.index(begin):keys.index(end) + len(end)]))
    pinned_archive = security / 'release.tar.gz'
    pinned_sig = security / 'release.asc'
    pinned_archive.write_bytes(source)
    pinned_sig.write_bytes(signature)
    result = subprocess.run(
        ['gpgv', '--homedir', security, '--keyring', key, '--status-fd', '1', pinned_sig, pinned_archive],
        env=env, capture_output=True, check=False,
    )
    (security / 'gpgv.status').write_bytes(result.stdout)
    (security / 'gpgv.log').write_bytes(result.stderr)
    identity = check_status(result.returncode, result.stdout.decode('ascii', errors='replace'), lock)
    verification = {
        'status': 'upstream_signature_verified',
        'archive_sha256': lock['archive_sha256'],
        'signature_sha256': lock['signature_sha256'],
        'release_keys_sha256': lock['release_keys_sha256'],
        'status_sha256': digest(security / 'gpgv.status'),
        **identity,
    }
    return source, verification


def run_logged(command, cwd, env, log):
    with log.open('wb') as output:
        subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)


def build(args):
    lock, lock_hash = metadata_snapshot(LOCK)
    inputs = {LOCK: lock_hash, BUILDER: digest(BUILDER), PROBE: digest(PROBE)}
    profile, profile_hash = metadata_snapshot(args.profile)
    sdk = args.sdk.resolve(strict=True)
    binding = verify_profile(profile, 'glibc', sdk)
    sdk_manifest = sdk / 'manifest.json'
    manifest, sdk_hash = metadata_snapshot(sdk_manifest, profile['sdk_binding']['sdk_manifest_sha256'])
    outputs = args.output.resolve()
    if outputs.is_relative_to(sdk) or outputs.is_relative_to(PORT):
        raise ValueError('OpenSSL output must be outside the SDK and the port inputs')

    tools = {}
    for suffix in ('gcc', 'ar', 'as', 'ld', 'ranlib'):
        name = 'x86_64-elf-' + suffix
        selected = tool_identity(name)
        if not selected['available'] or selected['sha256'] != manifest['tools'][name]['sha256']:
            raise ValueError(f'{name} differs from the verified SDK toolchain')
        tools[suffix] = selected
    for name, expected in lock['port_files'].items():
        if digest(PORT / name) != expected:
            raise ValueError(f'OpenSSL port input differs from the source lock: {name}')
        inputs[PORT / name] = expected

    outputs.mkdir(parents=True)
    env, _ = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    source, verification = release_snapshot(args, lock, outputs, env)
    staging = outputs / 'source'
    extract_verified_source(source, verification, staging)
    upstream = staging / lock['archive_root']
    if digest(upstream / 'LICENSE.txt') != lock['license_sha256']:
        raise ValueError('OpenSSL license differs from the source lock')
    run_logged(['patch', '--batch', '--fuzz=0', '-N', '-p1', '-i', PORT / 'xos-entropy.patch'],
               upstream, env, outputs / 'patch.log')
    shutil.copyfile(PORT / '99-xos.conf', upstream / 'Configurations/99-xos.conf')

    cross = outputs / 'tools'
    cross.mkdir()
    for name in ('as', 'ld'):
        (cross / name).symlink_to(tools[name]['path'])
    sysroot = sdk / 'sysroot'
    cflags = [
        '--sysroot=' + str(sysroot), '-B' + str(cross) + '/', '-nostdinc',
        '-isystem', str(sysroot / 'usr/include'), '-isystem', str(sysroot / 'usr/lib/compiler-include'),
        '-O2', '-mno-red-zone', '-fno-pie', '-fno-stack-protector',
        '-ffunction-sections', '-fdata-sections', '-D__xos__=1',
    ]
    env.update(CC=tools['gcc']['path'], AR=tools['ar']['path'], RANLIB=tools['ranlib']['path'],
               CFLAGS=shlex.join(cflags))
    make = select_gnu_make()['path']
    build_directory = outputs / 'build'
    build_directory.mkdir()
    options = [
        'xos-x86_64', '--prefix=/usr', '--openssldir=/etc/ssl', '--libdir=lib',
        'no-shared', 'no-dso', 'no-module', 'no-apps', 'no-tests', 'no-sock', 'no-dgram', 'no-quic',
        'no-async', 'no-secure-memory', '--with-rand-seed=getrandom',
    ]
    run_logged(['perl', upstream / 'Configure', *options], build_directory, env, outputs / 'configure.log')
    run_logged([make, '-j' + str(args.jobs), 'ARFLAGS=qcD', 'build_libs'],
               build_directory, env, outputs / 'build.log')

    prefix = outputs / 'prefix'
    run_logged([make, 'DESTDIR=' + str(prefix), 'install_dev'],
               build_directory, env, outputs / 'install.log')
    shutil.copyfile(upstream / 'LICENSE.txt', prefix / 'LICENSE.txt')
    libraries = [prefix / 'usr/lib' / name for name in LIBS]
    for archive in libraries:
        members = subprocess.check_output([tools['ar']['path'], 't', archive], env=env)
        if not members:
            raise ValueError(f'empty OpenSSL archive: {archive.name}')

    lib = sysroot / 'usr/lib'
    link_libraries = ['libc.a', 'libm.a', 'libgcc.a']
    link_libraries += [name for name in ('libxos_terminal.a', 'libgcc_eh.a')
                       if 'usr/lib/' + name in profile['sdk_binding']['link_artifacts']]
    start = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')
    end = ('crtend.o', 'crtn.o')
    fixture = outputs / 'openssl-probe.elf'
    run_logged([
        tools['gcc']['path'], *cflags, '-Wall', '-Wextra', '-Werror', '-I', prefix / 'usr/include',
        '-static', '-no-pie', '-nostdlib', '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
        '-T', sysroot / 'user.ld', '-o', fixture, *(lib / name for name in start), PROBE,
        '-Wl,--start-group', *libraries, *(lib / name for name in link_libraries), '-Wl,--end-group',
        *(lib / name for name in end),
    ], build_directory, env, outputs / 'link.log')
    headers = verify_elf(fixture)
    if verify_profile(profile, 'glibc', sdk) != binding or digest(args.profile) != profile_hash:
        raise ValueError('the SDK profile changed during the build')
    for path, expected in inputs.items():
        if digest(path) != expected:
            raise ValueError(f'OpenSSL input changed during the build: {path.name}')

    report = {
        'status': 'static_sdk_and_probe_linked',
        'source': verification,
        'source_lock_sha256': lock_hash,
        'builder_sha256': inputs[BUILDER],
        'sdk_manifest_sha256': sdk_hash,
        'sdk_profile_sha256': profile_hash,
        'sdk_binding': binding,
        'cross_tools': {name: tool['sha256'] for name, tool in tools.items()},
        'configure': options,
        'installed': {path.relative_to(prefix).as_posix(): digest(path)
                      for path in sorted(prefix.rglob('*')) if path.is_file()},
        'fixture_sha256': inputs[PROBE],
        'elf_sha256': digest(fixture),
        'program_headers': headers,
        'guest_qualification': 'not_run',
    }
    (outputs / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(fixture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'signature', 'release-keys', 'sdk', 'profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    build(args)


if __name__ == '__main__':
    main()
