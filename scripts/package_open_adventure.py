# SPDX-License-Identifier: Apache-2.0
"""Package an explicitly supplied, independently built XOS Open Adventure ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from xos_app import sdk_check
from xypm_format import (DEFAULT_PROFILE, MAX_FILE, canonical, check_profile,
                         inspect_elf, load_json, pack_package, require, sha_file)

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/adventure'
PACKAGE_ID = 'games.open_adventure'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def package(elf, receipt_path, sdk, profile_path, output):
    profile = load_json(profile_path)
    lock = load_json(PORT / 'source_lock.json')
    receipt = load_json(receipt_path)
    sdk_info = sdk_check(sdk, profile)
    require(receipt.get('format_version') == 1, 'unsupported build receipt')
    require(receipt.get('target_profile') == profile['id'], 'receipt profile mismatch')
    require(receipt.get('sdk_tree_sha256') == sdk_info['tree_sha256'], 'receipt SDK mismatch')
    require(receipt.get('output_sha256') == sha_file(elf), 'ELF does not match build receipt')
    require(receipt.get('upstream_archive_sha256') == lock['sha256'], 'upstream archive mismatch')
    require(receipt.get('generated_dungeon_sha256') == lock['data_sha256']['dungeon.c'] and
            receipt.get('generated_header_sha256') == lock['data_sha256']['dungeon.h'],
            'generated dungeon data differs from locked XOS build')
    inputs = {
        'adventure.yaml': PORT / 'adventure.yaml',
        'yaml.py': PORT / 'xos/yaml.py',
        'xos_readline.cpp': PORT / 'xos_readline.cpp',
        'readline.h': PORT / 'include/editline/readline.h',
        'patch': PORT / 'patches/0001_xos_runtime.patch',
        'build.sh': PORT / 'build.sh',
    }
    require(receipt.get('port_inputs') == {name: sha_file(path) for name, path in inputs.items()},
            'port inputs differ from build receipt')
    require(receipt.get('build_environment') and receipt.get('compiler'), 'build provenance missing')
    require(Path(elf).stat().st_size <= MAX_FILE, 'ELF exceeds XPK member limit')
    inspect_elf(elf)
    with tempfile.TemporaryDirectory(prefix='xos_adventure_xpk_') as folder:
        root = Path(folder)
        entries = []

        def add_bytes(path, data, role='data'):
            dest = root / path
            require(not dest.exists(), 'duplicate package path')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            entries.append({'path': path, 'type': 'file', 'size': len(data),
                            'sha256': digest(data), 'role': role})

        add_bytes('usr/bin/advent', Path(elf).read_bytes(), 'executable')
        license_paths = []
        notices = [('upstream/COPYING', PORT / 'upstream/COPYING'),
                   ('xos/LICENSE', ROOT / 'LICENSE'),
                   ('xos/NOTICE', ROOT / 'NOTICE'),
                   ('sdk/LICENSE', Path(sdk) / 'LICENSE'),
                   ('sdk/NOTICE', Path(sdk) / 'NOTICE'),
                   ('sdk/COPYING.NEWLIB', Path(sdk) / 'COPYING.NEWLIB')]
        for suffix, source in notices:
            dest = f'usr/share/licenses/{PACKAGE_ID}/{suffix}'
            add_bytes(dest, source.read_bytes())
            license_paths.append(dest)
        for source in sorted((Path(sdk) / 'licenses').rglob('*')):
            require(not source.is_symlink(), 'SDK notice symlink rejected')
            if source.is_file():
                relative = source.relative_to(Path(sdk) / 'licenses').as_posix()
                dest = f'usr/share/licenses/{PACKAGE_ID}/sdk/licenses/{relative}'
                add_bytes(dest, source.read_bytes())
                license_paths.append(dest)
        add_bytes(f'usr/share/{PACKAGE_ID}/source_lock.json', canonical(lock))
        add_bytes(f'usr/share/{PACKAGE_ID}/README.md', (PORT / 'README.md').read_bytes())
        embedded_receipt = dict(receipt)
        embedded_receipt['packager_sha256'] = sha_file(__file__)
        embedded_receipt['profile_sha256'] = digest(canonical(profile))
        embedded_receipt['provenance_scope'] = 'provided build receipt; ELF layout check is not runtime or toolchain authentication'
        receipt_data = canonical(embedded_receipt)
        receipt_dest = f'usr/share/{PACKAGE_ID}/build_receipt.json'
        add_bytes(receipt_dest, receipt_data)
        manifest = {
            'format_version': 1, 'id': PACKAGE_ID, 'upstream_version': lock['version'],
            'revision': 0, 'target_profile': profile['id'],
            'required_features': ['stdio', 'heap', 'file_io', 'cxx_runtime'],
            'runtime_dependencies': [], 'files': sorted(entries, key=lambda entry: entry['path']), 'licenses': license_paths,
            'build_receipt': {'path': receipt_dest, 'sha256': digest(receipt_data)},
            'source': lock['source'] + ' sha256=' + lock['sha256'] + '; local modifications in source_lock.json',
        }
        check_profile(manifest, profile)
        require(sdk_check(sdk, profile)['tree_sha256'] == sdk_info['tree_sha256'], 'SDK changed during packaging')
        require(sha_file(elf) == receipt['output_sha256'], 'ELF changed during packaging')
        require(receipt['port_inputs'] == {name: sha_file(path) for name, path in inputs.items()},
                'port inputs changed during packaging')
        result = pack_package(root, manifest, output)
    return {'status': 'packed_not_guest_tested', 'id': PACKAGE_ID,
            'package_sha256': sha_file(output), 'elf_sha256': sha_file(elf),
            'profile': profile['id'], 'output': str(Path(output).resolve()),
            'pack_result': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(package(args.elf, args.build_receipt, args.sdk, args.profile, args.output), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('open-adventure-package: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
