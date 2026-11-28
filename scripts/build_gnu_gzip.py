#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build authenticated GNU gzip and a gnulib consumer with an explicit XOS SDK."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

from glibc_g1_probe import select_gnu_make, tool_identity
from gnulib_xos import PORT as GNULIB_PORT, TARGET, configuration
from verify_glibc_source import check_status, decode_key, read_archive
from xypm_format import canonical, inspect_elf, load_json, require, sha_file
from xypm_sdk_profile import metadata_snapshot, require_stdio_marker, verify_profile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/gzip'
CONSUMER = ROOT / 'tests/fixtures/gnulib/consumer.c'
TOOLS = ('gcc', 'as', 'ld', 'ar', 'ranlib')


def verify_source(archive, lock, work):
    """Verify immutable archive/signature/key bytes before extracting them."""
    data = read_archive(archive, lock['archive_bytes'])
    signature = (PORT / 'keys/gzip_1_14.tar.xz.sig').read_bytes()
    key_path = PORT / 'keys/release_1_14.asc'
    key = key_path.read_bytes()
    for actual, expected, label in (
        (hashlib.sha256(data).hexdigest(), lock['sha256'], 'archive'),
        (hashlib.sha256(signature).hexdigest(), lock['signature_sha256'], 'signature'),
        (hashlib.sha256(key).hexdigest(), lock['public_key_sha256'], 'key'),
    ):
        require(actual == expected, 'gzip ' + label + ' differs from its source lock')
    verification = work / 'source_verification'
    verification.mkdir()
    keyring = verification / 'release_key.gpg'
    keyring.write_bytes(decode_key(key_path, data=key))
    frozen_archive = verification / archive.name
    frozen_archive.write_bytes(data)
    frozen_signature = verification / 'archive.sig'
    frozen_signature.write_bytes(signature)
    homedir = verification / 'home'
    homedir.mkdir(mode=0o700)
    verifier = tool_identity('gpgv')
    require(verifier.get('available'), 'gpgv is required')
    result = subprocess.run([verifier['path'], '--homedir', str(homedir),
                             '--status-fd', '1', '--keyring', str(keyring),
                             str(frozen_signature), str(frozen_archive)], capture_output=True)
    (verification / 'gpgv.status').write_bytes(result.stdout)
    (verification / 'gpgv.log').write_bytes(result.stderr)
    signer = lock['signer_primary_fingerprint']
    identity = check_status(result.returncode, result.stdout.decode('utf-8'),
                            {'signing_fingerprint': signer, 'primary_fingerprint': signer})
    require(sha_file(verifier['path']) == verifier['sha256'], 'signature verifier changed')
    return data, {'status': 'upstream_signature_verified', **identity,
                  'archive_sha256': lock['sha256'], 'signature_sha256': lock['signature_sha256'],
                  'public_key_sha256': lock['public_key_sha256'], 'verifier': verifier,
                  'status_sha256': sha_file(verification / 'gpgv.status')}


def build(args):
    archive = args.archive.resolve(strict=True)
    lock = load_json(PORT / 'source_lock.json')
    profile_path = args.profile.resolve(strict=True)
    profile, profile_digest = metadata_snapshot(profile_path)
    sdk = args.sdk.resolve(strict=True)
    binding = verify_profile(profile, 'glibc', sdk)
    require({'directories', 'stdio_transfer'} <= set(profile['features']),
            'gzip requires directories and stdio_transfer')
    metadata, sdk_digest = metadata_snapshot(sdk / 'manifest.json')
    require(sdk_digest == profile['sdk_binding']['sdk_manifest_sha256'], 'SDK identity changed')
    required = {'getrlimit', 'getdtablesize', 'fdopendir', 'lstat'}
    require(not required.intersection(metadata['stub_functions']),
            'SDK still lacks the native gnulib resource/directory prerequisites')
    tools = {name: tool_identity('x86_64-elf-' + name) for name in TOOLS}
    for name, tool in tools.items():
        require(tool.get('available') and tool['sha256'] == metadata['tools']['x86_64-elf-' + name]['sha256'],
                'cross tool differs from the selected SDK: ' + name)
    host_make = select_gnu_make()
    work = args.output_dir.resolve()
    require(not work.is_relative_to(sdk) and not work.is_relative_to(PORT),
            'build output must be outside the SDK and port inputs')
    work.mkdir(parents=True, exist_ok=False)
    source_inputs = [Path(__file__), ROOT / 'scripts/gnulib_xos.py', CONSUMER]
    for directory in (PORT, GNULIB_PORT):
        source_inputs += [path for path in sorted(directory.rglob('*')) if path.is_file()]
    inputs = {str(path.relative_to(ROOT)): sha_file(path) for path in source_inputs}
    report = {'schema': 1, 'status': 'preparing', 'version': lock['version'], 'target': TARGET,
              'runtime_family': 'glibc', 'profile': profile['id'], 'profile_sha256': profile_digest,
              'sdk_manifest_sha256': sdk_digest, 'sdk_binding': binding,
              'tools': tools, 'host_make': host_make, 'inputs': inputs, 'steps': [],
              'guest_qualification': 'not_run',
              'profile_limits': ['no asynchronous signal handlers',
                                  'no directory-fd-relative paths; use full paths',
                                  'no filesystem timestamp preservation or restoration',
                                  'mode copying succeeds only when projected output mode already matches',
                                  'no ownership changes; FAT projects uid/gid zero']}
    try:
        data, report['source_verification'] = verify_source(archive, lock, work)
        with tarfile.open(fileobj=io.BytesIO(data)) as package:
            package.extractall(work, filter='data')
        source = work / ('gzip-' + lock['version'])
        output = work / 'target'
        output.mkdir()
        env, report['sanitized_environment'] = configuration(
            sdk, metadata, tools, work, extra_cppflags=('-DNO_UTIME=1',))

        def run(name, command, cwd=output):
            log = work / (name + '.log')
            with log.open('wb') as stream:
                result = subprocess.run(list(map(str, command)), cwd=cwd, env=env,
                                        stdout=stream, stderr=subprocess.STDOUT)
            report['steps'].append({'step': name, 'returncode': result.returncode, 'log_sha256': sha_file(log)})
            require(result.returncode == 0, name + ' failed; see ' + str(log))

        for patch in sorted(GNULIB_PORT.glob('*.patch')):
            run(patch.stem, ['patch', '-p1', '-i', patch], cwd=source)
        for patch in sorted((PORT / 'patches').glob('*.patch')):
            run(patch.stem, ['patch', '-p1', '-i', patch], cwd=source)
        canonical_target = subprocess.check_output(['sh', source / 'build-aux/config.sub', TARGET],
                                                   env=env, text=True).strip()
        require(canonical_target == TARGET, 'config.sub did not recognize the real XOS target')
        triplet = subprocess.check_output(['sh', source / 'build-aux/config.guess'], env=env, text=True).strip()
        run('configure', [source / 'configure', '--build=' + triplet, '--host=' + TARGET,
                          '--prefix=/usr'])
        report['config_sha256'] = sha_file(output / 'lib/config.h')
        config = (output / 'lib/config.h').read_text()
        for name in ('HAVE_DECL_PROGRAM_INVOCATION_SHORT_NAME', 'HAVE_FDOPENDIR',
                     'HAVE_LSTAT', 'HAVE_GETDTABLESIZE'):
            require('#define ' + name + ' 1' in config, 'native gnulib prerequisite not selected: ' + name)
        run('compile', [host_make['path'], '-j' + str(args.jobs), 'all'])
        common = shlex.split(env['CC']) + shlex.split(env['CPPFLAGS']) + shlex.split(env['CFLAGS'])
        common += ['-I' + str(output / 'lib'), '-I' + str(source / 'lib')]
        run('consumer_compile', [*common, '-c', CONSUMER, '-o', work / 'consumer.o'])
        run('consumer_link', [*shlex.split(env['CC']), *shlex.split(env['LDFLAGS']),
                              work / 'consumer.o', output / 'lib/libgzip.a',
                              *shlex.split(env['LIBS']), '-o', work / 'gnulib_consumer.elf'])
        report['programs'] = {}
        for name, path in (('gzip', output / 'gzip'), ('gnulib_consumer', work / 'gnulib_consumer.elf')):
            layout = inspect_elf(path)
            require_stdio_marker(path.read_bytes(), name)
            report['programs'][name] = {'path': str(path.relative_to(work)), 'sha256': sha_file(path), 'layout': layout}
        require(sha_file(source / 'COPYING') == lock['license_sha256'], 'upstream license changed')
        shutil.copyfile(source / 'COPYING', work / 'COPYING')
        require(sha_file(archive) == lock['sha256']
                and all(sha_file(ROOT / name) == digest for name, digest in inputs.items()),
                'source or recipe changed during build')
        require(metadata_snapshot(profile_path)[1] == profile_digest
                and verify_profile(profile, 'glibc', sdk) == binding
                and all(sha_file(tool['path']) == tool['sha256'] for tool in (*tools.values(), host_make)),
                'SDK, profile or compiler changed during build')
        report['status'] = 'built_not_run'
    except BaseException as error:
        report.update(status='build_failed', error=str(error))
        raise
    finally:
        (work / 'manifest.json').write_bytes(canonical(report))
    print(work / 'manifest.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('archive', 'sdk', 'profile', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 32:
        parser.error('--jobs must be 1..32')
    try:
        build(args)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, 'GNU gzip build: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
