# SPDX-License-Identifier: Apache-2.0
"""Freeze the exact qualified single-runtime B2 SDK; never register an unknown SDK."""
import argparse
from pathlib import Path
import shutil
import tempfile
from xos_app import tree_receipt
from xypm_format import canonical, load_json, require, sha_file

ROOT=Path(__file__).resolve().parents[1]
SINGLE_SHA='1602f676c0c154ba3248bee29f41bb221001aa83ea3550c48b12087afcd0cb72'
CPP_SHA='e78726755d11d19feabcb7c36faebf6ed9a4e663f85f6beb081ffabae105a874'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--single-sdk',type=Path,default=ROOT/'build/sdk')
    parser.add_argument('--cpp-sdk',type=Path,default=ROOT/'build/releases/0.0.1-1024/xylophoneos_revival_0.0.1-1024_sdk')
    args=parser.parse_args()
    single,cpp=args.single_sdk.resolve(),args.cpp_sdk.resolve()
    profile=load_json(ROOT/'config/package/xos_x86_64_static_single_b2_v1.json')
    parent=ROOT/'.cache/xos_seed/xypm_sdk';parent.mkdir(parents=True,exist_ok=True)
    output=parent/'single_b2_v1'
    if output.exists():
        require(tree_receipt(output)[0] in profile['sdk_tree_sha256'],'existing frozen SDK changed')
        print(output);return
    require(tree_receipt(single)[0]==SINGLE_SHA,'single SDK differs from qualified B2 input')
    require(tree_receipt(cpp)[0]==CPP_SHA,'C++ SDK differs from qualified release input')
    with tempfile.TemporaryDirectory(prefix='prepare_',dir=parent) as folder:
        stage=Path(folder)/'sdk';shutil.copytree(single,stage)
        shutil.copytree(cpp/'cpp',stage/'cpp')
        shutil.copyfile(cpp/'target_runtime_provenance.json',stage/'target_runtime_provenance.json')
        shutil.copytree(cpp/'licenses',stage/'licenses/cpp_runtime_source')
        lineage={'format_version':1,'source_build_id':'911184be3f3c99f6',
                 'single_sdk_tree_sha256':SINGLE_SHA,'cpp_sdk_tree_sha256':CPP_SHA,
                 'cpp_runtime_provenance_sha256':sha_file(stage/'target_runtime_provenance.json'),
                 'scope':'single-runtime B2 stdio handoff; not a threaded SDK'}
        (stage/'xypm_sdk_lineage.json').write_bytes(canonical(lineage))
        require(tree_receipt(stage)[0] in profile['sdk_tree_sha256'],'composed SDK differs from registered snapshot')
        stage.rename(output)
    print(output)

if __name__=='__main__':main()
