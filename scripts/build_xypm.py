# SPDX-License-Identifier: Apache-2.0
"""Build the independent, read-only guest xypm package with a frozen SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from xos_app import build, init_project, pack
from xypm_format import DEFAULT_PROFILE,canonical,load_json,sha_file
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=DEFAULT_PROFILE)
    parser.add_argument('--fault-injection',action='store_true',help='build a test-only interruption fixture')
    args=parser.parse_args()
    profile=load_json(args.profile)
    source=ROOT/'src/user/programs/xypm.cpp'
    native_header=ROOT/'src/user/programs/xypm_native.hpp'
    journal_header=ROOT/'src/user/programs/xypm_journal.hpp'
    transaction_header=ROOT/'src/user/programs/xypm_transaction_impl.hpp'
    recovery_source=ROOT/'src/user/programs/xypm_recover.cpp'
    key=hashlib.sha256(canonical({'source':sha_file(source),'native_header':sha_file(native_header),'journal_header':sha_file(journal_header),'transaction_header':sha_file(transaction_header),'recovery_source':sha_file(recovery_source),'fault_injection':args.fault_injection,'text_header':sha_file(ROOT/'src/user/include/xos/text.hpp'),'build_script':sha_file(__file__),'builder':sha_file(ROOT/'scripts/xos_app.py'),'sdk_profile':profile})).hexdigest()[:20]
    folder=ROOT/'.cache/xos_seed/xypm'/key;folder.mkdir(parents=True,exist_ok=True)
    project=folder/'project'
    if not project.exists():
        init_project(project,'xos.xypm','cpp',profile)
        if args.fault_injection:(project/'src/main.cpp').write_bytes(b'#define XYP_TEST_FAULTS 1\n'+source.read_bytes())
        else:shutil.copyfile(source,project/'src/main.cpp')
        shutil.copyfile(native_header,project/'src/xypm_native.hpp')
        shutil.copyfile(journal_header,project/'src/xypm_journal.hpp')
        shutil.copyfile(transaction_header,project/'src/xypm_transaction_impl.hpp')
        (project/'src/xypm_recover.cpp').write_bytes(b'#define XYP_RECOVERY_LIBRARY 1\n'+recovery_source.read_bytes())
        (project/'src/xos').mkdir()
        shutil.copyfile(ROOT/'src/user/include/xos/text.hpp',project/'src/xos/text.hpp')
        feature_rows=''.join('    if (!__builtin_strcmp(name,'+json.dumps(name)+')) return true;\n' for name in profile['features'])
        profile_header=('// SPDX-License-Identifier: Apache-2.0\n#pragma once\n#include <cstring>\n'
                        '#define XYP_PACKAGE_PROFILE_ID '+json.dumps(profile['id'])+'\n'
                        'static inline bool xypm_profile_feature(const char* name) {\n'
                        +feature_rows+'    return false;\n}\n'
                        '#define XYP_PACKAGE_FEATURES(name) xypm_profile_feature(name)\n')
        (project/'src/xypm_profile.hpp').write_text(profile_header,encoding='utf-8')
        app=load_json(project/'xos_app.json')
        app['sources'].append('src/xypm_recover.cpp')
        if 'stdio_transfer' in profile['features']:app['required_features'].append('stdio_transfer')
        app['files'].append({'source':'src/xos/text.hpp','path':'usr/share/xos.xypm/source/xos/text.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_native.hpp','path':'usr/share/xos.xypm/source/xypm_native.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_journal.hpp','path':'usr/share/xos.xypm/source/xypm_journal.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_transaction_impl.hpp','path':'usr/share/xos.xypm/source/xypm_transaction_impl.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_recover.cpp','path':'usr/share/xos.xypm/source/xypm_recover.cpp','role':'data'})
        app['files'].append({'source':'src/xypm_profile.hpp','path':'usr/share/xos.xypm/source/xypm_profile.hpp','role':'data'})
        (project/'xos_app.json').write_bytes(canonical(app))
    receipt=build(project,args.sdk,profile)
    output=folder/'xypm.xpk'
    if output.exists():output.unlink()
    result=pack(project,args.sdk,profile,output)
    result['elf']=str(project/receipt['output']);result['cache_key']=key
    (folder/'manifest.json').write_bytes(canonical(result));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
