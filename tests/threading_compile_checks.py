# SPDX-License-Identifier: Apache-2.0
"""Receipt consistency and a second-ISA compile check; no host runtime substitute."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT = Path(__file__).resolve().parents[1]

def main():
    sdk = ROOT/'build/threading_sdk'
    manifest = json.loads((sdk/'manifest.json').read_text())
    for path,digest in manifest['artifacts'].items():
        assert hashlib.sha256((sdk/path).read_bytes()).hexdigest() == digest, path
    for path,digest in manifest['inputs'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == digest, 'stale SDK source '+path
    common = ROOT/'build/threading_common_compile.cpp'
    common.write_text('#include "thread_lifecycle.hpp"\nint check(xos::thread_lifetime& t) { return xos::thread_has_user_work(t); }\n')
    command = [shutil.which('clang++'),'--target=aarch64-none-elf','-std=c++20','-ffreestanding',
        '-nostdinc++','-fno-exceptions','-fno-rtti','-DXOS_THREADED_RUNTIME',
        '-I'+str(sdk/'include'),'-I'+str(ROOT/'src/user/include'),
        '-I'+str(ROOT/'src/shared/include'),'-I'+str(ROOT/'src/kernel/core')]
    commands=[]; logs=[]
    for source in [common,ROOT/'src/user/threading/pthread.cpp',ROOT/'src/user/threading/newlib_locks.cpp']:
        invocation=command+['-c',str(source),'-o',str(ROOT/'build'/('threading_aarch64_'+source.stem+'.o'))]
        result=subprocess.run(invocation,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        commands.append(invocation);logs.append(result.stdout)
        assert result.returncode == 0,result.stdout
    (ROOT/'build/threading_common_compile.log').write_text('\n'.join(logs))
    report={'status':'passed','checks':['SDK artifact/source SHA256 consistency','AArch64 common lifecycle/pthread/lock compile only'],
            'not_run':['AArch64 boot/runtime'],'commands':commands}
    (ROOT/'build/threading_compile_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS SDK receipt and common AArch64 compile checks (no second-ISA runtime claim)')
if __name__=='__main__':main()
