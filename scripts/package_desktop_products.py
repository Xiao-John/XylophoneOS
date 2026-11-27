#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build private xypm candidate packages for existing Mobius and ClarkE ELFs."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile

from mobius_build_receipt import packaged_build_binding
from xos_app import application_sdk_check, sdk_notices
from xypm_format import canonical, check_profile, inspect_elf, load_json, pack_package, require, sha_file
from xypm_sdk_profile import metadata_snapshot

ROOT = Path(__file__).resolve().parents[1]
CLARKE = ROOT / 'src/ports/aurora_browser'
QT = ROOT / 'src/ports/qt6'
FEATURES = ['cxx_runtime', 'file_io', 'heap', 'static_tls', 'stdio', 'threads']


def verify_elf(path, sdk_manifest, binding):
    receipt_path = path.with_suffix('.receipt.json')
    receipt, receipt_digest = metadata_snapshot(receipt_path)
    elf_digest = sha_file(path)
    require(elf_digest == receipt['elf_sha256'], f'ELF differs from receipt: {path}')
    require(receipt.get('sdk_tree_sha256') == binding['tree_sha256'], f'SDK tree differs from ELF receipt: {path}')
    inputs = receipt['inputs']
    require(inputs.get(str(sdk_manifest)) == sha_file(sdk_manifest), f'SDK differs from ELF receipt: {path}')
    if 'sdk_manifest_sha256' in binding:
        require(receipt.get('sdk_manifest_sha256') == binding['sdk_manifest_sha256'],
                f'glibc SDK manifest differs from ELF receipt: {path}')
        tools = load_json(sdk_manifest)['tools']
        for name in ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib'):
            require(receipt.get('target_tools', {}).get(name) == tools['x86_64-elf-' + name]['sha256'],
                    f'glibc target {name} differs from ELF receipt: {path}')
    for name, expected in inputs.items():
        require(sha_file(Path(name)) == expected, f'ELF build input changed: {name}')
    inspect_elf(path)
    payload = {'elf_sha256': elf_digest} | packaged_build_binding(receipt, receipt_digest)
    if 'widgets_kit_manifest_sha256' in receipt:
        kit_digest = receipt['widgets_kit_manifest_sha256']
        require('sdk_manifest_sha256' in binding and kit_digest in inputs.values(),
                f'Widgets kit is not bound to the product build inputs: {path}')
        payload['widgets_kit_manifest_sha256'] = kit_digest
    tls = receipt.get('network_profile', {}).get('controlled_tls')
    if tls is not None:
        require(receipt.get('runtime_family') == 'glibc', 'Controlled TLS requires the glibc browser build')
        payload['controlled_tls'] = tls
    return payload


def package(root, product, elfs, resources, notices, profile, sdk, revision, destination):
    entries = []
    binding = application_sdk_check(sdk, profile)

    def register(name, role):
        target = root / name
        entries.append({'path': name, 'type': 'file', 'role': role,
                        'size': target.stat().st_size, 'sha256': sha_file(target)})

    payloads = {}
    for name, path in elfs.items():
        payloads[name] = verify_elf(path, sdk / 'manifest.json', binding)
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
    widget_kits = {payload.get('widgets_kit_manifest_sha256') for payload in payloads.values()}
    if widget_kits != {None}:
        require(product == 'xos.mobius' and len(widget_kits) == 1 and None not in widget_kits,
                'Both Mobius executables must bind the same Widgets kit')
        notices = notices | {'QtBase-source-lock.json': QT / 'source_lock.json',
                             'Aurora-artwork-provenance.json': QT / 'aurora/assets/provenance.json'}
        gui = QT / 'licenses/gui'
        notices.update({f'qt/gui/{path.relative_to(gui).as_posix()}': path
                        for path in sorted(gui.rglob('*')) if path.is_file()})
    if any('controlled_tls' in payload for payload in payloads.values()):
        require(product == 'xos.clarke', 'Controlled browser TLS is only available for ClarkE')
        tls_root = CLARKE.parent / 'native_tls'
        tls_lock = load_json(tls_root / 'source_lock.json')
        notices = notices.copy()
        for name, digest in tls_lock['notices'].items():
            path = tls_root / 'notices' / name
            require(sha_file(path) == digest, 'Native TLS license differs from source lock: ' + name)
            notices['native_tls/' + name] = path
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
    portable_recipes = {'build_recipe_sha256' in payload for payload in payloads.values()}
    receipt = {'status': 'private_candidate', 'elfs': payloads,
               'sdk_tree_sha256': binding['tree_sha256']}
    if True in portable_recipes:
        require(product == 'xos.mobius' and portable_recipes == {True},
                'Mobius executables must use the same build receipt format')
        receipt['revision'] = revision
    if profile.get('runtime_family') == 'glibc':
        receipt.update(runtime_family='glibc', sdk_manifest_sha256=binding['sdk_manifest_sha256'],
                       profile_sha256=hashlib.sha256(canonical(profile)).hexdigest())
    else:
        receipt['sdk_build_id'] = binding['sdk_build_id']
    target.write_bytes(canonical(receipt))
    register(receipt_path, 'data')
    manifest = {'format_version': 1, 'id': product, 'upstream_version': '0.1.0', 'revision': revision,
                'target_profile': profile['id'], 'required_features': FEATURES,
                'runtime_dependencies': [], 'files': sorted(entries, key=lambda item: item['path']),
                'licenses': licenses, 'build_receipt': {'path': receipt_path, 'sha256': sha_file(target)},
                'source': 'XylophoneOS source and the verified private build receipts'}
    check_profile(manifest, profile)
    require(application_sdk_check(sdk, profile) == binding, 'SDK changed during product staging')
    return pack_package(root, manifest, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('product', choices=('mobius', 'clarke'))
    parser.add_argument('elf', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--revision', type=int, default=0)
    parser.add_argument('--sdk', type=Path, required=True, help='newlib SDK directory or glibc SDK build root')
    for name in ('profile', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if (args.product == 'mobius') != (args.session is not None):
        parser.error('--session is required for Mobius and applies only to Mobius')
    sdk = args.sdk.resolve(strict=True)
    profile = load_json(args.profile)
    require(profile.get('runtime_model') == 'threaded', 'desktop products require a threaded candidate profile')
    bundle = load_json(QT / 'redistribution_manifest.json')
    common = {'XOS-LICENSE': ROOT / 'LICENSE', 'XOS-NOTICE': ROOT / 'NOTICE'}
    if profile.get('runtime_family') == 'glibc':
        common.update({f'sdk/{name}': path for path, name in sdk_notices(sdk, profile, 'cpp')})
    else:
        require(profile['compiler_version'] == load_json(sdk / 'manifest.json')['compiler']['version'],
                'compiler version differs from profile')
        common['NEWLIB-COPYING'] = sdk / 'COPYING.NEWLIB'
    common.update({'Qt-MODIFICATIONS.md': QT / 'patches/MODIFICATIONS.md',
                   'Qt-redistribution.json': QT / 'redistribution_manifest.json'})
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
