#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Relink one isolated renderer-fault fixture from a fully bound browser bundle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

PORT=Path(__file__).resolve().parent;ROOT=PORT.parents[3]
sys.path[:0]=[str(ROOT/'scripts'),str(PORT.parent)]
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment,tool_identity
from target_inputs import digest,recheck_inputs
from xypm_sdk_profile import metadata_snapshot,verify_profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('bundle','sdk-build','sdk-profile','output'):
        parser.add_argument('--'+name,required=True,type=lambda value:Path(value).resolve())
    parser.add_argument('--fault-navigation',required=True,type=int);args=parser.parse_args()
    if args.fault_navigation<1: parser.error('select one positive diagnostic navigation')
    profile,profile_hash=metadata_snapshot(args.sdk_profile);binding=verify_profile(profile,'glibc',args.sdk_build)
    parent,parent_hash=metadata_snapshot(args.bundle/'manifest.json')
    if parent['status']!='clarke_webcore_browser_linked' or parent.get('test_profile') or parent['sdk_binding']!=binding or parent['sdk_profile_sha256']!=profile_hash:
        raise ValueError('require the complete production bundle and its exact SDK')
    inputs={ROOT/name:expected for name,expected in parent['inputs'].items()}
    inputs.update({args.bundle/name:expected for name,expected in parent['artifacts'].items()})
    inputs.update({args.bundle/name:expected for name,expected in parent['objects'].items()})
    inputs[args.bundle/'manifest.json']=parent_hash;inputs[Path(__file__)]=digest(Path(__file__))
    recheck_inputs(inputs)
    sdk,sdk_hash=metadata_snapshot(args.sdk_build/'manifest.json',parent['sdk_manifest_sha256'])
    tools={name:tool_identity('x86_64-elf-'+name) for name in ('gcc','g++','strip')}
    for name,tool in tools.items():
        if not tool.get('available') or (name!='strip' and tool['sha256']!=sdk['tools']['x86_64-elf-'+name]['sha256']):
            raise ValueError('fault fixture target tool changed')
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    env,_=clean_build_environment(os.environ)
    env.update(LC_ALL='C',COMPILER_PATH=str(args.bundle/'drivers/binutils'),XOS_ICU_SDK=str(args.sdk_build/'sysroot'),
        XOS_ICU_CC=tools['gcc']['path'],XOS_ICU_CXX=tools['g++']['path'],XOS_ICU_CXX_INCLUDES=str(args.bundle/'drivers/cxx-includes.txt'))
    record=dict(parent);record.update(status='building',parent_bundle_manifest_sha256=parent_hash,
        test_profile={'renderer_fault_navigation':args.fault_navigation},steps=[],guest_qualification='not_run')
    def save(): (out/'build_record.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    def run(stage,command):
        command=list(map(str,command));log=out/(stage+'.log')
        with log.open('w') as stream:
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        record['steps'].append({'stage':stage,'command':command,'returncode':result.returncode,'log_sha256':digest(log)});save()
        if result.returncode: raise RuntimeError(stage+' failed: '+str(log))
    save()
    try:
        compile=next(step['command'].copy() for step in parent['steps'] if step['stage']=='renderer')
        compile=[str(out/'renderer.o') if value==str(args.bundle/'renderer.o') else value for value in compile]
        compile.insert(1,'-DXOS_CLARKE_TEST_FAULT_NAVIGATION='+str(args.fault_navigation))
        run('renderer-fault',compile)
        link=next(step['command'].copy() for step in parent['steps'] if step['stage']=='link-renderer')
        link=[str(out/Path(value).name) if value in (str(args.bundle/'renderer.o'),str(args.bundle/'renderer.elf')) else value for value in link]
        run('link-renderer-fault',link);run('strip',[tools['strip']['path'],'--strip-debug',out/'renderer.elf'])
        headers=dict(parent['program_headers']);headers['renderer']=verify_elf(out/'renderer.elf')
        # Preserve the exact immutable UI/network/DOM baseline bytes without
        # another Qt or WebCore build. Each installed path is a regular file.
        for name in parent['artifacts']:
            if name!='renderer.elf': os.link(args.bundle/name,out/name)
        recheck_inputs(inputs)
        record.update(status='clarke_webcore_browser_linked',program_headers=headers,
            objects={'renderer.o':digest(out/'renderer.o')},
            artifacts={name:digest(out/name) for name in parent['artifacts']},
            inputs={str(path.relative_to(ROOT)):expected for path,expected in inputs.items()})
        save();(out/'manifest.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    except BaseException as error:
        record.update(status='failed',error=str(error));save();raise


if __name__=='__main__':main()
