#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the release daily XPK and native xypm with one glibc kit."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from xypm_format import canonical, require, sha_file
from xypm_sdk_profile import metadata_snapshot, verify_profile

ROOT = Path(__file__).resolve().parents[1]


def run(script, *arguments, capture=False):
    return subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, arguments)],
                          check=True, cwd=ROOT, text=True, capture_output=capture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('kit', 'sbase', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    kit, output = args.kit.resolve(strict=True), args.output.resolve()
    profile_path, sdk = kit / 'profile.json', kit / 'sdk'
    profile, profile_digest = metadata_snapshot(profile_path)
    binding = verify_profile(profile, 'glibc', sdk)
    require({'cxx_runtime', 'directories', 'stdio_transfer'} <= set(profile['features']),
            'stock installer requires a glibc C/C++ profile with directories and stdio_transfer')
    output.mkdir(parents=True, exist_ok=False)
    tools, runtime, package = output / 'tools', output / 'runtime', output / 'daily.xpk'
    run('build_daily_utilities.py', '--source', args.sbase.resolve(strict=True), '--sdk', sdk,
        '--glibc-profile', profile_path, '--output-dir', tools)
    run('stage_glibc_daily_runtime.py', '--sdk', sdk, '--profile', profile_path,
        '--tools', tools, '--output-dir', runtime)
    run('package_daily_utilities.py', '--tools', runtime, '--sdk', sdk, '--profile', profile_path,
        '--output', package)
    manager = json.loads(run('build_xypm.py', '--sdk', sdk, '--profile', profile_path, capture=True).stdout)
    source = Path(manager['elf'])
    receipt_path = source.parent / 'build_receipt.json'
    receipt, receipt_digest = metadata_snapshot(receipt_path)
    manager_digest = sha_file(source)
    require(receipt['runtime_family'] == 'glibc' and receipt['project_id'] == 'xos.xypm'
            and receipt['target_profile'] == binding['profile_id'] and receipt['output_sha256'] == manager_digest
            and receipt['sdk_manifest_sha256'] == profile['sdk_binding']['sdk_manifest_sha256']
            and all(receipt[key] == binding[key] for key in ('profile_sha256', 'sdk_tree_sha256')),
            'native xypm differs from the selected glibc SDK')
    manager_copy = output / 'xypm.elf'
    shutil.copyfile(source, manager_copy)
    shutil.copyfile(receipt_path, output / 'build_receipt.json')
    require(sha_file(manager_copy) == manager_digest and sha_file(output / 'build_receipt.json') == receipt_digest
            and verify_profile(metadata_snapshot(profile_path, profile_digest)[0], 'glibc', sdk) == binding,
            'stock installer inputs changed while building')
    (output / 'xypm.json').write_bytes(canonical({'elf': str(manager_copy), 'target_profile': binding['profile_id']}))
    print(json.dumps({'daily_xpk_sha256': sha_file(package), 'xypm_sha256': manager_digest,
                      'xypm_build_receipt_sha256': receipt_digest}, sort_keys=True))


if __name__ == '__main__':
    main()
