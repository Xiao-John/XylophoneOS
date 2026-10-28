# SPDX-License-Identifier: Apache-2.0
"""Interrupt every P2 transaction checkpoint and recover after a synced reboot."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes,pump
from xypm_format import canonical,load_json,require,sha_file,verify_package
from xypm_image import Disk,query_image,transact
from package_p2_verify_guest import fixtures,make_archive


def resources(guest):
    start=len(guest.output);send_bytes(guest,b'stats\r');guest.expect(b'completions=',start=start,timeout=40)
    pos=bytes(guest.output).find(b'completions=',start);guest.expect(b'\n',start=pos,timeout=40)
    match=re.search(rb'\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)',bytes(guest.output)[start:])
    require(match is not None,'missing complete resource counters')
    guest.expect_supervisor(start=pos,timeout=40)
    return tuple(int(value) for value in match.groups())


def sparse_copy(source,dest):
    with source.open('rb') as src,dest.open('xb') as dst:
        while True:
            data=src.read(1<<20)
            if not data:break
            if data.count(0)==len(data):dst.seek(len(data),os.SEEK_CUR)
            else:dst.write(data)
        dst.truncate(src.tell())


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--system',type=Path,required=True);parser.add_argument('--fault-build',type=Path,required=True);parser.add_argument('--profile',type=Path,default=ROOT/'config/package/xos_x86_64_static_single_b2_v1.json');parser.add_argument('--output',type=Path,required=True);parser.add_argument('--operation',choices=('install','upgrade','remove','all'),default='all');args=parser.parse_args()
    system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);manifest=load_json(system/'manifest.json');image=system/'xos.img';require(sha_file(image)==manifest['artifacts']['xos.img']['sha256'],'system image mismatch');build=load_json(args.fault_build);elf=Path(build['elf']);profile=load_json(args.profile)
    report={'status':'failed','system_build_id':manifest['build_id'],'image_sha256':sha_file(image),'fault_elf_sha256':sha_file(elf),'test_sha256':sha_file(Path(__file__)),'operations':{},'not_run':['power_loss','sector_tearing']};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p2_faults_') as temp:
            root=Path(temp);fixtures(root,profile,elf);original=root/'valid.xpk';old_manifest=copy.deepcopy(verify_package(original,profile)['manifest'])
            with tarfile.open(original,'r') as archive:old_bodies={entry['path']:archive.extractfile('payload/'+entry['path']).read() for entry in old_manifest['files']}
            old_entry=old_manifest['files'][0];old_bodies[old_entry['path']]=b'A'*6000;old_entry['size']=6000;old_entry['sha256']=hashlib.sha256(old_bodies[old_entry['path']]).hexdigest();v1=root/'v1.xpk';make_archive(v1,old_manifest,old_bodies);verify_package(v1,profile)
            new_manifest=copy.deepcopy(old_manifest);new_bodies=dict(old_bodies);new_manifest['upstream_version']='1.1';new_manifest['revision']=1;entry=new_manifest['files'][0];new_bodies[entry['path']]=b'B'*7000;entry['size']=7000;entry['sha256']=hashlib.sha256(new_bodies[entry['path']]).hexdigest();v2=root/'v2.xpk';make_archive(v2,new_manifest,new_bodies);verify_package(v2,profile)
            source=root/'source.img';create_fat32(source,512)
            with Disk(source,root) as backend:
                for path in ('/usr','/usr/bin','/usr/share','/out'):backend.command('mkdir',path)
                backend.command('import','/usr/bin/xypm',elf);backend.command('import','/out/v1.xpk',v1);backend.command('import','/out/v2.xpk',v2)
                sentinel=root/'sentinel';sentinel.write_bytes(b'user data');backend.command('import','/out/sentinel',sentinel)
            installed=root/'installed.img';transact(source,installed,profile,'install',package=v1)
            boot=root/'boot.img';shutil.copyfile(image,boot)
            def start(disk):
                g=Guest(boot,'package_p2_faults',work_disk=disk);g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=40);pump(g,1.0)
                if b'maintenance: persistent recovery required' not in g.output:
                    begin=len(g.output);send_bytes(g,b'demo quiet\r');g.expect_any((b'demo tasks stopped',b'demo tasks already stopped'),start=begin,timeout=40);g.expect_supervisor(start=begin,timeout=40)
                return g
            def command(g,line,expected,timeout=90):
                start_at=len(g.output);send_bytes(g,line.encode()+b'\r');match=g.expect_any((expected,b'xsh> '),start=start_at,timeout=timeout);require(match==expected,'unexpected result for '+line+': '+repr(bytes(g.output)[start_at:][-3000:]));g.expect_supervisor(start=start_at,timeout=timeout);return bytes(g.output)[start_at:]
            def verify_state(disk,operation,committed):
                listed=query_image(disk,profile,'list')['packages'];query_image(disk,profile,'verify-installed')
                expected_installed=(operation!='install') if not committed else (operation!='remove')
                require(bool(listed)==expected_installed,'wrong installed state '+operation)
                if expected_installed:
                    expected_version='1.1' if operation=='upgrade' and committed else '1.0'
                    require(len(listed)==1 and listed[0]['upstream_version']==expected_version,'wrong package version '+operation)
                with Disk(disk,root,True) as backend:
                    require(backend.export('/out/sentinel').read_bytes()==b'user data','user data changed')
                    for path in ('/var/lib/xypm/transaction','/var/lib/xypm/txdata','/var/lib/xypm/transaction_commit'):
                        require(backend.info(path) is None,'recovery marker remains '+path)
                    data=backend.info('/usr/share/p2/data.txt')
                    if expected_installed:
                        expected=b'B'*7000 if operation=='upgrade' and committed else b'A'*6000
                        require(data is not None and backend.export('/usr/share/p2/data.txt').read_bytes()==expected,'wrong package data')
                    else:require(data is None,'package data unexpectedly exists')
            selected=('install','upgrade','remove') if args.operation=='all' else (args.operation,)
            for operation in selected:
                base=source if operation=='install' else installed;target='/out/v1.xpk' if operation=='install' else '/out/v2.xpk' if operation=='upgrade' else 'friends.p2'
                probe=root/(operation+'_probe.img');sparse_copy(base,probe);guest=start(probe);baseline=resources(guest)
                output=command(guest,'maint-run /usr/bin/xypm '+operation+' '+target+' --fault-after 99999',b'maintenance: completed')
                match=re.search(rb'xypm-test: checkpoints=(\d+)',output);require(match,'missing checkpoint count');total=int(match.group(1));require(total>0,'empty checkpoint set');guest.close();(out/(operation+'_probe.log')).write_bytes(guest.output);guest=None;verify_state(probe,operation,True);probe.unlink()
                report['operations'][operation]={'checkpoints':total,'passed':[]}
                for step in range(1,total+1):
                    trial=root/(operation+'_trial.img');sparse_copy(base,trial);guest=start(trial);before=resources(guest)
                    output=command(guest,'maint-run /usr/bin/xypm '+operation+' '+target+' --fault-after '+str(step),b'maintenance: retained')
                    require(('xypm-test: injected='+str(step)).encode() in output,'requested checkpoint was not reached')
                    require(resources(guest)==before,'resources drift after interrupted worker');guest.close();(out/(operation+'_'+str(step)+'_interrupted.log')).write_bytes(guest.output);guest=None
                    with Disk(trial,root,True) as backend:
                        pending=any(backend.info(path) is not None for path in ('/var/lib/xypm/transaction','/var/lib/xypm/txdata','/var/lib/xypm/transaction_commit'))
                    guest=start(trial);before=resources(guest)
                    if pending:
                        command(guest,'maint-recover-boot',b'maintenance: completed');require(resources(guest)==before,'resources drift after recovery')
                    guest.close();(out/(operation+'_'+str(step)+'_recovery.log')).write_bytes(guest.output);guest=None
                    verify_state(trial,operation,step==total)
                    report['operations'][operation]['passed'].append(step);trial.unlink()
                    (out/'fault_report.json').write_bytes(canonical(report))
            report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'fault_report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
