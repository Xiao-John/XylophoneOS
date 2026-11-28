#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Link the production OpenSSL/net2 fetcher into an isolated real-guest probe."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PORT=ROOT/'src/ports/webkit/browser'
sys.path[:0]=[str(ROOT/'scripts'),str(PORT.parent),str(PORT)]
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from target_inputs import digest, recheck_inputs
from tls_policy import write_policy
from xypm_sdk_profile import metadata_snapshot, verify_profile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-build','sdk-profile','openssl','tls-root-der','output'):
        parser.add_argument('--'+name,required=True,type=lambda value:Path(value).resolve())
    parser.add_argument('--tls-origin',required=True); parser.add_argument('--tls-address',required=True)
    args=parser.parse_args()
    profile,profile_hash=metadata_snapshot(args.sdk_profile)
    binding=verify_profile(profile,'glibc',args.sdk_build)
    sdk,sdk_hash=metadata_snapshot(args.sdk_build/'manifest.json',profile['sdk_binding']['sdk_manifest_sha256'])
    ssl,ssl_hash=metadata_snapshot(args.openssl/'report.json')
    if ssl['status']!='static_sdk_and_probe_linked' or ssl['sdk_manifest_sha256']!=sdk_hash or ssl['sdk_profile_sha256']!=profile_hash:
        raise ValueError('OpenSSL and probe require the same complete SDK')
    tools={name:tool_identity('x86_64-elf-'+name) for name in ('gcc','g++','as','ld','strip')}
    for name,tool in tools.items():
        if not tool.get('available') or (name!='strip' and tool['sha256']!=sdk['tools']['x86_64-elf-'+name]['sha256']):
            raise ValueError('mismatched target tool: '+name)
    inputs={args.sdk_profile:profile_hash,args.sdk_build/'manifest.json':sdk_hash,args.openssl/'report.json':ssl_hash,
            args.tls_root_der:digest(args.tls_root_der),Path(__file__):digest(Path(__file__))}
    for name,expected in ssl['installed'].items(): inputs[args.openssl/'prefix'/name]=expected
    for directory in (ROOT/'src/user/include/xos',ROOT/'src/shared/include/xos',ROOT/'src/ports/browser_http'):
        inputs.update({path:digest(path) for path in directory.rglob('*') if path.is_file()})
    for path in (PORT/'https.cpp',PORT/'https.hpp',PORT/'tls_policy.py',
                 PORT.parent/'icu/xos-compiler',ROOT/'tests/fixtures/webkit/https_probe.cpp'):
        inputs[path]=digest(path)
    recheck_inputs(inputs)
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    drivers=out/'drivers';(drivers/'binutils').mkdir(parents=True)
    (drivers/'cxx').symlink_to(PORT.parent/'icu/xos-compiler')
    for name in ('as','ld'): (drivers/'binutils'/name).symlink_to(tools[name]['path'])
    includes=drivers/'includes.txt';includes.write_text('\n'.join(profile['sdk_binding']['cxx_runtime']['include_directories'])+'\n')
    policy=write_policy(args.tls_origin,args.tls_address,args.tls_root_der,out/'tls_policy.hpp')
    inputs[out/'tls_policy.hpp']=digest(out/'tls_policy.hpp')
    env,removed=clean_build_environment(os.environ)
    env.update(LC_ALL='C',COMPILER_PATH=str(drivers/'binutils'),XOS_ICU_SDK=str(args.sdk_build/'sysroot'),
        XOS_ICU_CC=tools['gcc']['path'],XOS_ICU_CXX=tools['g++']['path'],XOS_ICU_CXX_INCLUDES=str(includes))
    report={'status':'building','sdk_manifest_sha256':sdk_hash,'sdk_profile_sha256':profile_hash,
            'sdk_binding':binding,'openssl_report_sha256':ssl_hash,'policy':policy,'steps':[],
            'sanitized_environment':removed,'guest_qualification':'not_run'}
    def save(): (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    def run(stage,command):
        command=list(map(str,command));log=out/(stage+'.log')
        with log.open('w') as stream:
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        report['steps'].append({'stage':stage,'command':command,'returncode':result.returncode,'log_sha256':digest(log)})
        save()
        if result.returncode: raise RuntimeError(stage+' failed: '+str(log))
    save()
    try:
        common=[drivers/'cxx','-std=c++20','-O2','-g0','-ffunction-sections','-fdata-sections',
            '-I',out,'-I',PORT,'-I',ROOT/'src/shared/include','-I',ROOT/'src/user/include','-I',args.openssl/'prefix/usr/include']
        objects=[]
        for name,path in (('probe',ROOT/'tests/fixtures/webkit/https_probe.cpp'),('https',PORT/'https.cpp'),
                         ('http',ROOT/'src/ports/browser_http/http.cpp'),('transport',ROOT/'src/ports/browser_http/transport.cpp')):
            obj=out/(name+'.o');objects.append(obj);run(name,[*common,'-c',path,'-o',obj])
        elf=out/'https_probe.elf'
        run('link',[drivers/'cxx','-Wl,--gc-sections,--no-keep-memory',*objects,'-Wl,--start-group',
            args.openssl/'prefix/usr/lib/libssl.a',args.openssl/'prefix/usr/lib/libcrypto.a','-Wl,--end-group','-o',elf])
        run('strip',[tools['strip']['path'],'--strip-debug',elf])
        headers=verify_elf(elf);recheck_inputs(inputs)
        if verify_profile(profile,'glibc',args.sdk_build)!=binding: raise ValueError('SDK changed during probe build')
        report.update(status='linked',elf_sha256=digest(elf),program_headers=headers,
            inputs={str(path.relative_to(ROOT)):value for path,value in inputs.items()})
        save()
    except BaseException as error:
        report.update(status='failed',error=str(error));save();raise


if __name__=='__main__': main()
