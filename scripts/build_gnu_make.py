#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-build the pinned GNU Make for the XOS static glibc profile."""
import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile

from glibc_g1_probe import clean_build_environment, select_gnu_make, tool_identity
from xypm_format import canonical, inspect_elf, load_json, require, sha_file
from xypm_sdk_profile import metadata_snapshot, require_stdio_marker, verify_profile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/gnu_make'
TOOLS = ('gcc', 'as', 'ld', 'ar', 'ranlib')


def verify_source(lock, archive, signature, keyring, log):
    require(sha_file(archive) == lock['sha256'] and sha_file(signature) == lock['signature_sha256'],
            'GNU Make archive or signature differs from the source lock')
    with log.open('wb') as output:
        result = subprocess.run(['gpgv', '--status-fd', '1', '--keyring', str(keyring),
                                 str(signature), str(archive)], stdout=output, stderr=subprocess.STDOUT)
    signer = lock['signer_primary_fingerprint']
    signatures = [line.split() for line in log.read_text(errors='replace').splitlines()
                  if line.startswith('[GNUPG:] VALIDSIG ')]
    require(result.returncode == 0 and any(parts[-1] == signer for parts in signatures),
            'GNU Make signature verification failed; see ' + str(log))


def configuration(sdk, metadata, tools, work):
    sysroot = sdk / 'sysroot'
    lib = sysroot / 'usr/lib'
    tool_dir = work / 'tools'
    tool_dir.mkdir()
    for name, tool in tools.items():
        (tool_dir / name).symlink_to(tool['path'])
    flags = ['--sysroot=' + str(sysroot), '-B' + str(tool_dir) + '/',
             '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
             '-ftls-model=local-exec']
    includes = ['-D__xos__=1', '-I' + str(PORT), '-nostdinc', '-isystem',
                str(sysroot / 'usr/include'), '-isystem', str(lib / 'compiler-include')]
    start = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o', 'xos_stdio_receiver.o')
    libraries = ('libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a')
    end = ('crtend.o', 'crtn.o')
    links = ['-T', str(sysroot / 'user.ld'), *(str(lib / name) for name in start),
             '-Wl,--start-group', *(str(lib / name) for name in libraries),
             '-Wl,--end-group', *(str(lib / name) for name in end)]
    env, _ = clean_build_environment(os.environ)
    for name in list(env):
        if name.startswith(('ac_cv_', 'make_cv_', 'gl_cv_')) or name in ('MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS'):
            del env[name]
    site = work / 'config.site'
    missing = set(metadata['stub_functions']) | {'pselect', 'mkfifo', 'fork', 'vfork'}
    require(all(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name) for name in missing),
            'invalid SDK stub name')
    site.write_text(''.join('ac_cv_func_' + name + '=no\n' for name in sorted(missing))
                    + 'make_cv_synchronous_posix_spawn=yes\nmake_cv_sys_gnu_glob=no\n')
    env.update(LC_ALL='C', CC=shlex.join([tools['gcc']['path'], *flags]),
               AR=tools['ar']['path'], RANLIB=tools['ranlib']['path'],
               CFLAGS='-O2 -ffunction-sections -fdata-sections', CPPFLAGS=shlex.join(includes),
               LDFLAGS='-nostdlib -static -no-pie -Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
               LIBS=shlex.join(links), CONFIG_SITE=str(site))
    return env


def build(args):
    lock = load_json(PORT / 'source_lock.json')
    profile, profile_digest = metadata_snapshot(args.profile)
    sdk = args.sdk.resolve(strict=True)
    binding = verify_profile(profile, 'glibc', sdk)
    require('stdio_transfer' in profile['features'], 'GNU Make needs the stdio transfer runtime')
    sdk_digest = profile['sdk_binding']['sdk_manifest_sha256']
    metadata, _ = metadata_snapshot(sdk / 'manifest.json', sdk_digest)
    tools = {name: tool_identity('x86_64-elf-' + name) for name in TOOLS}
    for name, tool in tools.items():
        require(tool.get('available') and tool.get('sha256') == metadata['tools']['x86_64-elf-' + name]['sha256'],
                'cross tool differs from the SDK build: ' + name)
    host_make = select_gnu_make()
    work = args.output_dir.resolve()
    require(not work.is_relative_to(sdk) and not work.is_relative_to(PORT),
            'output must be outside the SDK and port source')
    work.mkdir(parents=True, exist_ok=False)
    archive, signature, keyring = (path.resolve(strict=True) for path in (args.archive, args.signature, args.keyring))
    port_files = [Path(__file__), *(path for path in sorted(PORT.rglob('*')) if path.is_file())]
    port_hashes = {str(path.relative_to(ROOT)): sha_file(path) for path in port_files}
    report = {'status': 'preparing', 'version': lock['version'], 'target': lock['target'],
              'archive_sha256': lock['sha256'], 'signature_sha256': lock['signature_sha256'],
              'upstream_keyring_sha256': sha_file(keyring), 'profile_sha256': profile_digest,
              'sdk_manifest_sha256': sdk_digest, 'sdk_tree_sha256': binding['sdk_tree_sha256'],
              'tools': tools, 'host_make': host_make, 'inputs': port_hashes, 'steps': [],
              'guest_qualification': 'not_run'}
    receipt = work / 'manifest.json'
    try:
        verify_source(lock, archive, signature, keyring, work / 'source_verification.log')
        report['source_verified_signer'] = lock['signer_primary_fingerprint']
        with tarfile.open(archive) as source_archive:
            source_archive.extractall(work, filter='data')
        source = work / ('make-' + lock['version'])
        output = work / 'target'
        output.mkdir()
        env = configuration(sdk, metadata, tools, work)

        def run(name, command, cwd=output):
            log = work / (name + '.log')
            with log.open('wb') as stream:
                result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
            report['steps'].append({'step': name, 'returncode': result.returncode, 'log_sha256': sha_file(log)})
            require(result.returncode == 0, name + ' failed; see ' + str(log))

        for patch in sorted((PORT / 'patches').glob('*.patch')):
            run(patch.stem, ['patch', '-p1', '-i', str(patch)], cwd=source)
        triplet = subprocess.check_output(['sh', source / 'build-aux/config.guess'], env=env, text=True).strip()
        run('configure', [source / 'configure', '--build=' + triplet, '--host=' + lock['target'],
                          '--prefix=/usr', '--disable-nls', '--disable-load', '--without-guile',
                          '--enable-posix-spawn'])
        config = output / 'src/config.h'
        require('#define USE_POSIX_SPAWN 1' in config.read_text(), 'core must build with POSIX spawn')
        report['config_sha256'] = sha_file(config)
        run('compile', [host_make['path'], '-j2', 'all'])
        elf = output / 'make'
        layout = inspect_elf(elf)
        require_stdio_marker(elf.read_bytes(), 'GNU Make')
        require(sha_file(archive) == lock['sha256'] and sha_file(signature) == lock['signature_sha256']
                and sha_file(keyring) == report['upstream_keyring_sha256']
                and all(sha_file(ROOT / name) == digest for name, digest in port_hashes.items()),
                'upstream or port input changed during the build')
        require(metadata_snapshot(args.profile)[1] == profile_digest and verify_profile(profile, 'glibc', sdk) == binding
                and all(sha_file(tool['path']) == tool['sha256'] for tool in (*tools.values(), host_make)),
                'SDK, profile or toolchain changed during the build')
        shutil.copyfile(source / 'COPYING', work / 'COPYING')
        report.update(status='built_not_run', elf={'path': 'target/make', 'sha256': sha_file(elf), 'layout': layout})
    except BaseException:
        report['status'] = 'build_failed'
        raise
    finally:
        receipt.write_bytes(canonical(report))
    print(receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'signature', 'keyring', 'sdk', 'profile', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    try:
        build(parser.parse_args())
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, 'GNU Make build: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
