# SPDX-License-Identifier: Apache-2.0
"""Compose a candidate SDK and profile from a built system and frozen C++ SDK."""
import argparse
from pathlib import Path
import shutil
import sys

from sdk_receipt import verify_sdk
from xos_app import tree_receipt
from xypm_format import canonical, load_json, require, sha_file

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--cpp-sdk', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='must not exist')
    args = parser.parse_args()
    try:
        system = args.system.resolve(strict=True); source = system/'sdk'
        cpp = args.cpp_sdk.resolve(strict=True)
        manifest = load_json(system/'manifest.json')
        verified = verify_sdk(source, manifest)
        registered = load_json(ROOT/'config/package/xos_x86_64_static_single_b2_v1.json')
        cpp_hash = tree_receipt(cpp)[0]
        require(cpp_hash in registered['sdk_tree_sha256'], 'C++ SDK is not registered B2 snapshot')
        require(manifest['artifacts']['xos.img']['sha256'] == sha_file(system/'xos.img'), 'system image changed')
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        sdk = output/'sdk'; shutil.copytree(source, sdk)
        shutil.copytree(cpp/'cpp', sdk/'cpp')
        shutil.copyfile(cpp/'target_runtime_provenance.json', sdk/'target_runtime_provenance.json')
        shutil.copytree(cpp/'licenses/cpp_runtime_source', sdk/'licenses/cpp_runtime_source')
        digest = tree_receipt(sdk)[0]
        require(verify_sdk(source, manifest) == verified and tree_receipt(cpp)[0] == cpp_hash,
                'input SDK changed during composition')
        profile = {'format_version':1, 'id':'xos-x86_64-daily-p2-candidate-v1',
                   'architecture':'x86_64', 'byte_order':'little', 'word_bits':64,
                   'runtime_model':'single', 'syscall_abi':1, 'startup_version':3,
                   'compiler_version':'16.2.0', 'layout':'e08_static_tls_main_stack_128k_c3_stdio',
                   'features':['stdio','heap','file_io','directories','static_tls','cxx_runtime',
                               'stdio_transfer','spawn_delegate'],
                   'sdk_tree_sha256':[digest], 'verified_system_builds':[manifest['build_id']],
                   'scope':'candidate only; qualification bound to independently executed checks',
                   'evidence':'docs/work_log/0069_daily_utilities.md'}
        (output/'profile.json').write_bytes(canonical(profile))
        receipt = {'status':'prepared_not_qualified', 'system_build_id':manifest['build_id'],
                   'image_sha256':sha_file(system/'xos.img'), 'system_sdk_tree':tree_receipt(source)[0],
                   'cpp_sdk_tree':cpp_hash, 'composed_sdk_tree':digest,
                   'profile_sha256':sha_file(output/'profile.json'), 'builder_sha256':sha_file(__file__)}
        (output/'lineage.json').write_bytes(canonical(receipt))
        print(canonical(receipt).decode(),end='')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('daily-sdk: '+str(error),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
