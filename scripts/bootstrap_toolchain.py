#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Export or restore the repository's pinned, relocatable Linux toolchain bundle."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile

from toolchain import LOCK, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--prefix', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--bundle', type=Path, required=True)
    restore.add_argument('--sha256', required=True)
    restore.add_argument('--prefix', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'export':
        export_bundle(args.prefix.resolve(), args.output.resolve())
    else:
        restore_bundle(args.bundle.resolve(), args.sha256, args.prefix.resolve())


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def toolchain_environment(prefix):
    return {'PATH': str(prefix / 'bin') + os.pathsep + os.environ.get('PATH', ''),
            'CROSS_PREFIX': str(prefix / 'bin/x86_64-elf-'),
            'NASM': str(prefix / 'bin/nasm'), 'QEMU': str(prefix / 'bin/qemu-system-x86_64')}


def check_tools(prefix):
    previous = dict(os.environ)
    try:
        os.environ.update(toolchain_environment(prefix))
        checked = audit()
        qemu = prefix / 'bin/qemu-system-x86_64'
        version = subprocess.check_output([str(qemu), '--version'], text=True).splitlines()[0]
        if not version.startswith('QEMU emulator version ' + LOCK['qemu'] + ' '):
            if version != 'QEMU emulator version ' + LOCK['qemu']:
                raise ValueError('QEMU version differs from config/toolchain.json')
        checked['qemu'] = {'version': version, 'sha256': sha(qemu)}
        return checked
    finally:
        os.environ.clear()
        os.environ.update(previous)


def inventory(prefix):
    files = {}
    for path in sorted(prefix.rglob('*')):
        relative = path.relative_to(prefix).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if Path(target).is_absolute() or not path.resolve().is_relative_to(prefix):
                raise ValueError('toolchain must use internal relative symlinks: ' + relative)
            files[relative] = {'symlink': target}
        elif path.is_file():
            files[relative] = {'sha256': sha(path), 'mode': path.stat().st_mode & 0o777}
        elif not path.is_dir():
            raise ValueError('unsupported toolchain entry: ' + relative)
    return files


def export_bundle(prefix, output):
    if output.exists() or output.is_relative_to(prefix):
        raise ValueError('bundle must be a new file outside the toolchain prefix')
    checked = check_tools(prefix)
    files = inventory(prefix)
    content = json.dumps({'version': 1, 'lock': LOCK, 'files': files}, sort_keys=True, indent=2).encode() + b'\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:xz') as bundle:
        manifest = tarfile.TarInfo('toolchain_manifest.json')
        manifest.size = len(content)
        manifest.mode = 0o644
        bundle.addfile(manifest, io.BytesIO(content))
        for relative in files:
            path = prefix / relative
            entry = bundle.gettarinfo(str(path), arcname='toolchain/' + relative)
            entry.uid = entry.gid = entry.mtime = 0
            entry.uname = entry.gname = ''
            if entry.isfile():
                with path.open('rb') as stream:
                    bundle.addfile(entry, stream)
            else:
                bundle.addfile(entry)
    print(json.dumps({'bundle': str(output), 'sha256': sha(output), 'tools': checked}, indent=2))


def restore_bundle(bundle_path, expected, prefix):
    if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected) or sha(bundle_path) != expected:
        raise ValueError('toolchain bundle SHA256 mismatch')
    if prefix.exists():
        raise ValueError('choose a new toolchain prefix; existing installations are not overwritten')
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.xos-toolchain-', dir=prefix.parent) as temporary:
        staging = Path(temporary)
        with tarfile.open(bundle_path, 'r:*') as bundle:
            manifest = json.load(bundle.extractfile('toolchain_manifest.json'))
            if not isinstance(manifest, dict) or manifest.get('version') != 1 or manifest.get('lock') != LOCK:
                raise ValueError('bundle does not match config/toolchain.json')
            if not isinstance(manifest.get('files'), dict) or not all(isinstance(name, str) for name in manifest['files']):
                raise ValueError('bundle requires a file inventory')
            names = [member.name for member in bundle.getmembers()]
            if len(names) != len(set(names)) or set(names) != {'toolchain_manifest.json', *('toolchain/' + name for name in manifest['files'])}:
                raise ValueError('bundle member list differs from its manifest')
            bundle.extractall(staging, filter='data')
        staged = staging / 'toolchain'
        restored = inventory(staged)
        for name, entry in restored.items():
            expected_entry = manifest['files'].get(name)
            if 'mode' in entry and isinstance(expected_entry, dict):
                mode = expected_entry.get('mode')
                if type(mode) is not int or not 0 <= mode <= 0o777:
                    raise ValueError('invalid ordinary file mode in toolchain manifest')
                entry['mode'] = mode
        if restored != manifest['files']:
            raise ValueError('restored toolchain differs from its manifest')
        # The data filter deliberately changes ordinary modes (0444 to 0644,
        # for example). Restore them only after validating all bytes and links.
        for name, entry in restored.items():
            if 'mode' in entry:
                (staged / name).chmod(entry['mode'])
        check_tools(staged)
        staged.rename(prefix)
    checked = check_tools(prefix)
    activation = prefix / 'activate.sh'
    activation.write_text('# SPDX-License-Identifier: Apache-2.0\n' +
        'export PATH=' + shlex.quote(str(prefix / 'bin')) + ':"$PATH"\n' +
        ''.join('export ' + name + '=' + shlex.quote(value) + '\n'
                for name, value in toolchain_environment(prefix).items() if name != 'PATH'))
    receipt = {'status': 'restored_and_version_checked', 'bundle_sha256': expected,
               'lock': LOCK, 'tools': checked, 'guest_qualification': 'not_run'}
    (prefix / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print('Restored toolchain: ' + str(prefix))
    print('source ' + shlex.quote(str(activation)))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit('toolchain bootstrap: ' + str(error))
