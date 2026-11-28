#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild, package and independently qualify a glibc host SDK on Linux x86-64."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request

from package_glibc_host_sdk import LOCK, ROOT, source_snapshot, tree


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(path.read_text())


def run(command, *, cwd=None):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, check=True)


def download(url, destination, expected):
    with urllib.request.urlopen(url, timeout=120) as response, destination.open('xb') as output:
        shutil.copyfileobj(response, output)
    if sha(destination) != expected:
        raise ValueError('download SHA-256 mismatch: ' + destination.name)


def validate(output):
    package = load(output / 'package.json')
    for field in ('archive', 'source_archive'):
        asset = package[field]
        if Path(asset['name']).name != asset['name'] or sha(output / asset['name']) != asset['sha256']:
            raise ValueError('completed archive differs: ' + field)
    # Only the final SDK root and this empty consumer directory are mounted.
    # The launcher does not inherit the build checkout or build SDK mounts.
    with tempfile.TemporaryDirectory(prefix='.sdk-consumer-', dir=output.parent) as temporary:
        check = Path(temporary)
        run(['tar', '--zstd', '-xf', output / package['archive']['name'], '-C', check])
        sdk = check / package['archive']['name'].removesuffix('.tar.zst')
        if tree(sdk, exclude=('file-manifest.json',)) != load(sdk / 'file-manifest.json'):
            raise ValueError('fresh extraction differs from the packaged file manifest')
        consumer = check / 'consumer'
        consumer.mkdir()
        run([sdk / 'xos-sdk', '--workdir', consumer, 'xos-sdk-smoke'])
        result = load(consumer / 'sdk-smoke/qualification.json')
        if (result['status'] != 'passed' or result['source_commit'] != package['source_commit'] or
                result['profile_sha256'] != package['profile_sha256'] or
                result['system'] != package['system'] or result['binding'] != package['binding']):
            raise ValueError('consumer qualification does not bind the completed archive')
        result['archive'] = package['archive']
        result['source_archive'] = package['source_archive']
        result['fresh_extraction_verified'] = True
        result['consumer_mount'] = 'empty consumer directory only; SDK root read-only'
        (output / 'qualification.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    # Publish a fixed asset set, excluding build trees, raw command logs and disks.
    assets = [package['archive']['name'], package['source_archive']['name'], 'package.json', 'qualification.json']
    (output / 'SHA256SUMS').write_text(''.join(sha(output / name) + '  ' + name + '\n' for name in assets))
    notes = ('# XOS glibc host SDK prerelease\n\n'
             'Linux x86-64 SDK with static glibc 2.44 C/C++ applications as the default. '
             'The unchanged Preview 2 host tools are included. Its former newlib target SDK '
             'is retained separately under `legacy/newlib`.\n\n'
             'The release was built from `' + package['source_commit'] + '` and its final archive '
             'was freshly extracted. With only an empty consumer work directory mounted, the '
             'installed SDK completed C/C++ init/build/check/pack and ran the packaged ELF bytes '
             'in the included ISO using QEMU TCG. Both applications exited 0 and restored their '
             'resource baselines. C checked glibc version and file contents; C++ checked vector, '
             'thread and exception behavior.\n\n'
             'Download the binary archive and matching sources archive, then verify `SHA256SUMS`. '
             'The sources include the exact GNU glibc and GCC archives, signatures/key material, '
             'and XOS build recipes. `package.json` and `qualification.json` bind this build; '
             'they do not reuse any earlier qualification identity.\n\n'
             'This preview covers the static C/C++ application SDK and the included native '
             'system. It is separate from the complete glibc userland/runtime distribution. '
             'Keep old newlib application profiles and package disks separate.\n')
    (output / 'release-notes.md').write_text(notes)
    print('Final archive independently qualified: ' + package['archive']['name'], flush=True)


def build(args):
    if not re.fullmatch(r'xos-sdk-glibc-preview-[0-9]+', args.tag):
        raise ValueError('use a new numbered glibc preview tag')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT):
        raise ValueError('commit the source changes before building a release')
    output = args.output.resolve()
    if output.exists():
        raise ValueError('release output must not exist')
    output.parent.mkdir(parents=True, exist_ok=True)
    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    sources, sdks = work / 'sources', work / 'sdk'
    sources.mkdir()
    sdks.mkdir()
    repo = work / 'worktrees/release'
    source_snapshot(repo)
    lock = load(LOCK)
    base_archive = sdks / (lock['base_name'] + '.tar.zst')
    download(lock['base_url'], base_archive, lock['base_sha256'])
    glibc = load(ROOT / 'src/ports/glibc/source_lock.json')
    gcc = load(ROOT / 'src/ports/gcc/source_lock.json')
    gcc_auth = load(ROOT / 'src/ports/gcc/shared_source_auth.json')
    for url, filename, digest in (
        (glibc['upstream_url'], glibc['archive'], glibc['archive_sha256']),
        (gcc['source_url'], gcc['source_archive'], gcc['sha256']),
        (gcc_auth['signature_url'], gcc['source_archive'] + '.sig', gcc_auth['signature_sha256']),
        (gcc_auth['keyring_url'], 'gnu-keyring.gpg', gcc_auth['keyring_sha256']),
    ):
        download(url, sources / filename, digest)
    run(['tar', '--zstd', '-xf', base_archive, '-C', sdks])
    launcher = sdks / lock['base_name'] / 'xos-sdk'

    def inside(arguments):
        # Source/build paths are fixed inside the isolated Preview 2 environment.
        run([launcher, '--workdir', work, '/bin/bash', '-c',
             'cd /work/worktrees/release && exec "$@"', 'sdk-build', *arguments])

    inside(['python3', 'scripts/build_glibc_sdk.py', '--archive', '/work/sources/glibc-2.44.tar.xz',
            '--output', 'build/glibc-c', '--jobs', str(args.jobs)])
    inside(['python3', 'scripts/build_glibc_static_cxx.py', '--archive', '/work/sources/gcc-16.2.0.tar.xz',
            '--signature', '/work/sources/gcc-16.2.0.tar.xz.sig', '--keyring', '/work/sources/gnu-keyring.gpg',
            '--sdk-build', 'build/glibc-c', '--output', 'build/glibc-cxx', '--jobs', str(args.jobs)])
    inside(['python3', 'scripts/create_xypm_profile.py', 'create', '--runtime-family', 'glibc',
            '--sdk-build', 'build/glibc-cxx', '--id', 'xos-x86_64-glibc-host-' + commit[:12], '--cxx',
            '--feature', 'directories', '--feature', 'threads', '--feature', 'stdio_transfer',
            '--output', 'build/profile.json'])
    inside(['python3', 'scripts/package_glibc_sdk.py', '--sdk-build', 'build/glibc-cxx',
            '--profile', 'build/profile.json', '--output', 'build/kit'])
    inside(['python3', 'scripts/build.py', '--output-dir', 'build/system', '--quiet-demos-on-launch'])
    inside(['python3', 'scripts/license_audit.py', '--build', 'build/system'])
    inside(['python3', 'scripts/package_glibc_host_sdk.py', '--base-archive',
            '/work/sdk/' + base_archive.name, '--kit', 'build/kit', '--system', 'build/system',
            '--sources', '/work/sources', '--tag', args.tag, '--source-commit', commit,
            '--output', '/work/release'])
    shutil.move(work / 'release', output)
    validate(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build')
    create.add_argument('--tag', required=True)
    create.add_argument('--workdir', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--jobs', type=int, choices=range(1, 9), default=2)
    check = commands.add_parser('validate')
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'build':
        build(args)
    else:
        validate(args.output.resolve(strict=True))


if __name__ == '__main__':
    main()
