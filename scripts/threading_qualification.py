# SPDX-License-Identifier: Apache-2.0
"""Bind passed guest reports to the exact kernel, SDK and compiled payloads."""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'build'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    kernel=json.loads((BUILD/'manifest.json').read_text())
    sdk_path=BUILD/'threading_sdk/manifest.json'
    sdk=json.loads(sdk_path.read_text())
    probes=json.loads((BUILD/'threading_probe_manifest.json').read_text())
    assert probes['sdk_manifest_sha256']==sha(sdk_path),'stale probe SDK binding'
    for path,digest in sdk['inputs'].items():
        assert sha(ROOT/path)==digest,'stale SDK source '+path
    for path,digest in sdk['artifacts'].items():
        assert sha(BUILD/'threading_sdk'/path)==digest,'stale SDK artifact '+path
    for path,digest in probes['artifacts'].items():
        assert sha(BUILD/path)==digest,'stale guest payload '+path
    reports={}
    for name in ['threading_report','threading_pthread_report','threading_cpp_report','threading_compile_report',
                 'process_smoke_report','runtime_smoke_report','task_smoke_report','libc_smoke_report','persist_smoke_report','license_report']:
        path=BUILD/(name+'.json')
        report=json.loads(path.read_text())
        assert report['status']=='passed',name
        version=report.get('build_id',report.get('kernel_build_id',kernel['build_id']))
        assert version==kernel['build_id'],name+' uses a different kernel build'
        reports[name]={'sha256':sha(path),'checks':report.get('checks',[])}
    assert json.loads((BUILD/'threading_pthread_report.json').read_text())['payload_sha256']==probes['artifacts']['threading_pthread_probe.elf']
    assert json.loads((BUILD/'threading_cpp_report.json').read_text())['payload_sha256']==probes['artifacts']['threading_cpp_probe.elf']
    # Recheck every input hashed by the ordinary system builder as well.
    for path,digest in kernel['sources'].items():
        assert sha(ROOT/path)==digest,'stale system source '+path
    qemu=Path(shutil.which(os.environ.get('QEMU','qemu-system-x86_64'))).resolve()
    result={'status':'passed_scoped_T0_T1_T2','base_commit':'9c896df90c2d589989b5888a495108b36959c684',
            'kernel_build_id':kernel['build_id'],'boot_image_sha256':sha(BUILD/'xos.img'),
            'kernel_elf_sha256':sha(BUILD/'kernel.elf'),'kernel_binary_bytes':(BUILD/'kernel.bin').stat().st_size,
            'sdk_manifest_sha256':sha(sdk_path),'probe_manifest_sha256':sha(BUILD/'threading_probe_manifest.json'),
            'source_profile':sdk['profile'],
            'qemu':{'path':str(qemu),'sha256':sha(qemu),'version':subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0]},
            'configuration':{'machine':'pc-i440fx-10.0','cpu':'qemu64','ram_mib':512,'smp':1,'network':'none','clock_resolution_ns':10000000},
            'tools':kernel['tools'],'archives':{p:d for p,d in sdk['artifacts'].items() if p.endswith('.a')},
            'reports':reports,'not_run':['SMP','full POSIX pthread compliance','CPython T3-PY','Qt T3-QT',
            'long-duration/random scheduling stress','second-ISA runtime','native GCC/G++ compiler guest regression']}
    native=BUILD/'threading_native_report.json'
    if native.exists():
        report=json.loads(native.read_text())
        assert report['status']=='passed' and report['build_id']==kernel['build_id'],'native compiler regression not passed for this build'
        result['reports']['threading_native_report']={'sha256':sha(native),'checks':report['checks']}
        result['not_run'].remove('native GCC/G++ compiler guest regression')
    (BUILD/'threading_qualification.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS scoped T0/T1/T2 qualification | kernel',kernel['build_id'])
if __name__=='__main__':main()
