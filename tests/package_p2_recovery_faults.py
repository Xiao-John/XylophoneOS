# SPDX-License-Identifier: Apache-2.0
"""Interrupt each recovery mutation and retry using the immutable boot image."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes,pump
from xypm_format import canonical,load_json,require,sha_file
from xypm_image import Disk
from package_p2_faults import sparse_copy
from package_p2_journal_recovery import journal_bytes
import hashlib


def build_probe(sdk,output):
    compiler=shutil.which('x86_64-elf-gcc');libgcc=subprocess.check_output([compiler,'-print-libgcc-file-name'],text=True).strip()
    subprocess.run([compiler,'-O2','-mno-red-zone','-fno-pie','-fno-pic','-fno-stack-protector','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-fno-use-cxa-atexit','-DXYP_RECOVERY_TEST=1','-idirafter',str(sdk/'include'),'-nostdlib','-static','-no-pie','-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(ROOT/'src/user/programs/xypm_recover.cpp'),'-Wl,--start-group',str(sdk/'lib/libxos.a'),libgcc,'-Wl,--end-group','-o',str(output)],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--system',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);manifest=load_json(system/'manifest.json');image=system/'xos.img';require(sha_file(image)==manifest['artifacts']['xos.img']['sha256'],'system image mismatch');probe=out/'recovery_fault.elf';build_probe(system/'sdk',probe)
    report={'status':'failed','system_build_id':manifest['build_id'],'image_sha256':sha_file(image),'probe_sha256':sha_file(probe),'test_sha256':sha_file(Path(__file__)),'operations':{},'not_run':['power_loss','sector_tearing']};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_recovery_faults_') as temp:
            root=Path(temp);boot=root/'boot.img';shutil.copyfile(image,boot)
            rows=[{'path':'/usr/share/p2/changed','old':b'old contents','new':b'new contents'},
                  {'path':'/usr/share/p2/removed','old':b'removed original','new':None},
                  {'path':'/usr/share/p2/newdir/newfile','old':None,'new':b'new file'}]
            journal,rows,digest=journal_bytes(rows,['/usr/share/p2/newdir']);commit=b'XYPCMT1\0'+digest;commit+=hashlib.sha256(commit).digest()
            def temp_file(name,body):
                path=root/name;path.write_bytes(body);return path
            def make_base(case):
                disk=root/(case+'_base.img');create_fat32(disk,512)
                with Disk(disk,root) as backend:
                    for path in ('/var','/var/lib','/var/lib/xypm','/var/lib/xypm/txdata','/var/lib/xypm/txdata/old','/var/lib/xypm/txdata/new','/usr','/usr/share','/usr/share/p2','/usr/share/p2/newdir','/out'):backend.command('mkdir',path)
                    backend.command('import','/out/recover_fault',probe);backend.command('import','/var/lib/xypm/transaction',temp_file('journal',journal))
                    for index,row in enumerate(rows):
                        old,new=row.get('old'),row.get('new')
                        if new is not None:backend.command('import',row['path'],temp_file('target_'+str(index),new))
                        if old is not None:backend.command('import','/var/lib/xypm/txdata/old/%08d'%index,temp_file('old_'+str(index),old))
                    if case=='committed':backend.command('import','/var/lib/xypm/txdata/committed',temp_file('commit',commit))
                return disk
            def start(disk):
                g=Guest(boot,'package_p2_recovery_faults',work_disk=disk);g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=40);pump(g,0.8);return g
            def command(g,line,expected,timeout=90):
                begin=len(g.output);send_bytes(g,line.encode()+b'\r');matched=g.expect_any((expected,b'xsh> '),start=begin,timeout=timeout);require(matched==expected,'unexpected result '+line+': '+repr(bytes(g.output)[begin:][-3000:]));g.expect_supervisor(start=begin,timeout=timeout);return bytes(g.output)[begin:]
            def verify(disk,case):
                with Disk(disk,root,True) as backend:
                    for path in ('/var/lib/xypm/transaction','/var/lib/xypm/txdata','/var/lib/xypm/transaction_commit'):require(backend.info(path) is None,'recovery marker remains '+path)
                    for row in rows:
                        expected=row.get('new') if case=='committed' else row.get('old');found=backend.info(row['path'])
                        if expected is None:require(found is None,'unexpected destination '+row['path'])
                        else:require(found is not None and backend.export(row['path']).read_bytes()==expected,'incorrect destination '+row['path'])
            for case in ('rollback','committed'):
                base=make_base(case);sample=root/(case+'_sample.img');sparse_copy(base,sample);guest=start(sample);baseline=resources(guest)
                result=command(guest,'maint-recover /out/recover_fault 99999',b'maintenance: completed');match=re.search(rb'xypm-recover-test: checkpoints=(\d+)',result);require(match,'missing recovery checkpoint count');total=int(match.group(1));require(total>0,'empty recovery checkpoint set');require(resources(guest)==baseline,'resources drift');guest.close();(out/(case+'_sample.log')).write_bytes(guest.output);guest=None;verify(sample,case);sample.unlink()
                report['operations'][case]={'checkpoints':total,'passed':[]}
                for step in range(1,total+1):
                    disk=root/(case+'_trial.img');sparse_copy(base,disk);guest=start(disk);baseline=resources(guest)
                    result=command(guest,'maint-recover /out/recover_fault '+str(step),b'maintenance: retained');require(('xypm-recover-test: injected='+str(step)).encode() in result,'checkpoint not reached');require(resources(guest)==baseline,'resources drift after injected recovery failure');guest.close();(out/(case+'_'+str(step)+'_failure.log')).write_bytes(guest.output);guest=None
                    with Disk(disk,root,True) as backend:pending=any(backend.info(path) is not None for path in ('/var/lib/xypm/transaction','/var/lib/xypm/txdata','/var/lib/xypm/transaction_commit'))
                    guest=start(disk);baseline=resources(guest)
                    if pending:command(guest,'maint-recover-boot',b'maintenance: completed');require(resources(guest)==baseline,'resources drift after recovery retry')
                    guest.close();(out/(case+'_'+str(step)+'_retry.log')).write_bytes(guest.output);guest=None;verify(disk,case)
                    report['operations'][case]['passed'].append(step);(out/'recovery_fault_report.json').write_bytes(canonical(report));disk.unlink()
            report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'recovery_fault_report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
