#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build private xypm candidate packages for existing Mobius and ClarkE ELFs."""
import argparse
from pathlib import Path
import shutil
import tempfile

from xos_app import sdk_check
from xypm_format import canonical, check_profile, inspect_elf, load_json, pack_package, require, sha_file

ROOT = Path(__file__).resolve().parents[1]
CLARKE = ROOT / 'src/ports/aurora_browser'
QT = ROOT / 'src/ports/qt6'
FEATURES = ['cxx_runtime', 'file_io', 'heap', 'static_tls', 'stdio', 'threads']


def verify_elf(path, sdk_manifest, sdk_tree_digest):
    receipt_path = path.with_suffix('.receipt.json')
    receipt = load_json(receipt_path)
    elf_digest = sha_file(path)
    require(elf_digest == receipt['elf_sha256'], f'ELF differs from receipt: {path}')
    require(receipt.get('sdk_tree_sha256') == sdk_tree_digest, f'SDK tree differs from ELF receipt: {path}')
    inputs = receipt['inputs']
    require(inputs.get(str(sdk_manifest)) == sha_file(sdk_manifest), f'SDK differs from ELF receipt: {path}')
    for name, expected in inputs.items():
        require(sha_file(Path(name)) == expected, f'ELF build input changed: {name}')
    inspect_elf(path)
    return {'elf_sha256': elf_digest, 'build_receipt_sha256': sha_file(receipt_path)}


def package(root, product, elfs, resources, notices, profile, sdk, revision, destination):
    entries = []
    binding = sdk_check(sdk, profile)

    def register(name, role):
        target = root / name
        entries.append({'path': name, 'type': 'file', 'role': role,
                        'size': target.stat().st_size, 'sha256': sha_file(target)})

    payloads = {}
    for name, path in elfs.items():
        payloads[name] = verify_elf(path, sdk / 'manifest.json', binding['tree_sha256'])
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        register(name, 'executable')
        require(entries[-1]['sha256'] == payloads[name]['elf_sha256'], 'ELF changed during staging')
    for name, path in resources.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        register(name, 'data')
    licenses = []
    for name, path in notices.items():
        filename = f'usr/share/licenses/{product}/{name}'
        target = root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        register(filename, 'data')
        licenses.append(filename)

    receipt_path = f'usr/share/{product}/build_receipt.json'
    target = root / receipt_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical({'status': 'private_candidate', 'elfs': payloads,
                                  'sdk_tree_sha256': binding['tree_sha256'],
                                  'sdk_build_id': binding['sdk_build_id']}))
    register(receipt_path, 'data')
    manifest = {'format_version': 1, 'id': product, 'upstream_version': '0.1.0', 'revision': revision,
                'target_profile': profile['id'], 'required_features': FEATURES,
                'runtime_dependencies': [], 'files': sorted(entries, key=lambda item: item['path']),
                'licenses': licenses, 'build_receipt': {'path': receipt_path, 'sha256': sha_file(target)},
                'source': 'XylophoneOS source and the verified private build receipts'}
    check_profile(manifest, profile)
    return pack_package(root, manifest, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product', choices=('mobius', 'clarke'))
    parser.add_argument('elf', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--revision', type=int, default=0)
    for name in ('sdk', 'profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if (args.product == 'mobius') != (args.session is not None):
        parser.error('--session is required for Mobius and applies only to Mobius')
    sdk = args.sdk.resolve(strict=True)
    profile = load_json(args.profile)
    require(profile.get('runtime_model') == 'threaded', 'desktop products require a threaded candidate profile')
    require(profile['compiler_version'] == load_json(sdk / 'manifest.json')['compiler']['version'],
            'compiler version differs from profile')

    bundle = load_json(QT / 'redistribution_manifest.json')
    common = {'XOS-LICENSE': ROOT / 'LICENSE', 'XOS-NOTICE': ROOT / 'NOTICE',
              'NEWLIB-COPYING': sdk / 'COPYING.NEWLIB',
              'Qt-MODIFICATIONS.md': QT / 'patches/MODIFICATIONS.md',
              'Qt-redistribution.json': QT / 'redistribution_manifest.json'}
    for item in bundle['license_texts']:
        path = ROOT / item['path']
        common['qt/' + path.name] = path
    clarke_notices = common | {f'browser/{path.name}': path
                              for path in sorted((CLARKE / 'licenses').glob('*')) if path.is_file()}
    clarke_data = {f'usr/share/xos.clarke/web/{name}': CLARKE / 'pages' / name for name in
                   ('start.html', 'reading.html', 'garden.html', 'garden.bmp', 'theme.css')}
    name = 'xos.' + args.product
    elfs = {f'usr/bin/{args.product}.elf': args.elf.resolve(strict=True)}
    if args.product == 'mobius':
        elfs['usr/bin/mobius-session.elf'] = args.session.resolve(strict=True)
        resources, notices = {}, common
    else:
        resources, notices = clarke_data, clarke_notices
    with tempfile.TemporaryDirectory(prefix='xos_desktop_product_') as temporary:
        result = package(Path(temporary), name, elfs, resources, notices, profile, sdk,
                         args.revision, args.output)
        print(f"{args.output}: {result['sha256']}")


if __name__ == '__main__':
    main()
