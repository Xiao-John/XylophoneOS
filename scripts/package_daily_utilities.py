# SPDX-License-Identifier: Apache-2.0
"""Package a frozen daily utility build into an xypm candidate XPK."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from xos_app import sdk_notices, tree_receipt
from xypm_format import canonical, check_profile, inspect_elf, load_json, pack_package, require, sha_file
from xypm_sdk_profile import GLIBC_STDIO_RECEIVER, metadata_snapshot, require_stdio_marker, verify_profile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/sbase'
PACKAGE_ID = 'xos.daily_utilities'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True,
                        help='newlib SDK directory or glibc SDK build directory')
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        tools = args.tools.resolve(strict=True)
        sdk = args.sdk.resolve(strict=True)
        registry = load_json(PORT / 'daily_utilities.json')
        build = load_json(tools / 'manifest.json')
        profile = load_json(args.profile)
        glibc = profile.get('runtime_family') == 'glibc'
        if glibc:
            binding = verify_profile(profile, 'glibc', sdk)
            require({'directories', 'stdio_transfer'} <= set(profile['features']),
                    'daily glibc package needs directory and stdio receiver admission')
            digest = binding['sdk_tree_sha256']
            metadata, manifest_sha = metadata_snapshot(
                sdk / 'manifest.json', profile['sdk_binding']['sdk_manifest_sha256'])
            sdk_files = metadata['artifacts']
            require(build.get('runtime_family') == 'glibc'
                    and build.get('sdk_manifest_sha256') == manifest_sha
                    and build.get('profile_sha256') == binding['profile_sha256']
                    and build.get('stdio_receiver_sha256')
                    == profile['sdk_binding']['link_artifacts'][GLIBC_STDIO_RECEIVER],
                    'glibc utility build does not bind the verified SDK, profile, and receiver')
        else:
            digest, sdk_files = tree_receipt(sdk)
            require(build.get('runtime_family', 'newlib') == 'newlib', 'daily utility runtime family mismatch')
        require(digest in profile['sdk_tree_sha256'] and build['sdk_tree_sha256'] == digest,
                'SDK differs from build or profile')
        require(build['registry_sha256'] == sha_file(PORT / 'daily_utilities.json'), 'registry changed')
        require(build['builder_sha256'] == sha_file(ROOT / 'scripts/build_daily_utilities.py'), 'builder changed')
        require(build['compiler']['target'] == 'x86_64-elf' and
                build['compiler']['version'] == profile['compiler_version'], 'compiler target/version mismatch')
        expected = registry['tools']
        actual = build['tools']
        require(len(actual) == len(expected), 'tool count mismatch')
        with tempfile.TemporaryDirectory(prefix='xos_daily_xpk_') as folder:
            root = Path(folder); entries = []; license_paths = []
            def add(path, data, role='data'):
                dst = root / path
                require(not dst.exists(), 'duplicate staged file')
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(data)
                entries.append({'path': path, 'type': 'file', 'role': role, 'size': len(data),
                                'sha256': hashlib.sha256(data).hexdigest()})
            for wanted, item in zip(expected, actual):
                require(all(item.get(key) == wanted[key] for key in ('name', 'source', 'license', 'scope')),
                        'utility registry mismatch')
                name = wanted['name']; source = PORT / wanted['source']; elf = tools / name
                require(not source.is_symlink() and not elf.is_symlink() and
                        source.resolve().is_relative_to(PORT.resolve()) and elf.resolve().is_relative_to(tools),
                        'utility source or ELF escapes root')
                require(sha_file(source) == item['source_sha256'], 'utility source changed: ' + name)
                payload = elf.read_bytes()
                require(hashlib.sha256(payload).hexdigest() == item['elf_sha256']
                        and len(payload) == item['size'], 'utility ELF changed: ' + name)
                require(item['guest_path'] == '/usr/bin/' + name, 'unexpected install path')
                add(item['guest_path'][1:], payload, 'executable')
                inspect_elf(root / item['guest_path'][1:])
                if glibc:
                    require_stdio_marker(payload, name)
            notices = [('upstream/LICENSE', PORT / 'upstream/LICENSE'), ('xos/LICENSE', ROOT / 'LICENSE'),
                       ('xos/NOTICE', ROOT / 'NOTICE')]
            for suffix, path in notices:
                destination = f'usr/share/licenses/{PACKAGE_ID}/{suffix}'
                add(destination, path.read_bytes()); license_paths.append(destination)
            for path, name in sdk_notices(sdk, profile, 'c'):
                data = path.read_bytes()
                require(hashlib.sha256(data).hexdigest() == sdk_files.get(name), 'SDK notice changed: ' + name)
                destination = f'usr/share/licenses/{PACKAGE_ID}/sdk/{name}'
                add(destination, data); license_paths.append(destination)
            receipt_path = f'usr/share/{PACKAGE_ID}/build_receipt.json'
            receipt = canonical(build); add(receipt_path, receipt)
            add(f'usr/share/{PACKAGE_ID}/daily_utilities.json', canonical(registry))
            add(f'usr/share/{PACKAGE_ID}/source_lock.json', (PORT / 'source_lock.json').read_bytes())
            manifest = {'format_version': 1, 'id': PACKAGE_ID, 'upstream_version': '0.1.0', 'revision': 0,
                        'target_profile': profile['id'], 'required_features': ['stdio','heap','file_io','directories','stdio_transfer'],
                        'runtime_dependencies': [], 'files': sorted(entries, key=lambda e: e['path']),
                        'licenses': license_paths, 'build_receipt': {'path': receipt_path,
                        'sha256': hashlib.sha256(receipt).hexdigest()},
                        'source': 'XOS utility sources and pinned sbase source in embedded build receipt and source lock'}
            check_profile(manifest, profile)
            if glibc:
                require(verify_profile(load_json(args.profile), 'glibc', sdk) == binding,
                        'glibc SDK or profile changed during packaging')
            else:
                require(tree_receipt(sdk)[0] == digest, 'SDK changed during packaging')
            result = pack_package(root, manifest, args.output)
        print(json.dumps({'status':'candidate_packed', 'id':PACKAGE_ID, 'sha256':result['sha256'],
                          'files':result['payload_files'], 'profile':profile['id'], 'output':str(args.output)}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('daily-utilities-package: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
