# SPDX-License-Identifier: Apache-2.0
"""Exercise immutable boot recovery on isolated journal and disk states."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes,pump
from xypm_format import canonical,require,sha_file
from xypm_image import Disk


def journal_bytes(rows, directories):
    rows=sorted(rows,key=lambda item:item['path'].lower())
    directories=sorted(directories,key=str.lower)
    def pack_string(value):
        value=value.encode('ascii');require(len(value)<256,'fixture path too long');return value+b'\0'*(256-len(value))
    packed=[]
    for row in rows:
        old=row.get('old');new=row.get('new');flags=(1 if old is not None else 0)|(2 if new is not None else 0)
        packed.append(struct.pack('<256sIII32s32s',pack_string(row['path']),flags,len(old or b''),len(new or b''),
            hashlib.sha256(old).digest() if old is not None else bytes(32),
            hashlib.sha256(new).digest() if new is not None else bytes(32)))
    body=b''.join(packed)+b''.join(struct.pack('<256sI',pack_string(path),1) for path in directories)
    prefix=struct.pack('<8sIIII',b'XYPTXN1\0',1,len(rows),len(directories),0)
    digest=hashlib.sha256(prefix+body).digest()
    return prefix+digest+body,rows,digest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--system',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((system/'manifest.json').read_text());image=system/'xos.img';require(sha_file(image)==manifest['artifacts']['xos.img']['sha256'],'system image mismatch')
    report={'status':'failed','system_build_id':manifest['build_id'],'image_sha256':sha_file(image),'test_sha256':sha_file(Path(__file__)),
            'checks':[],'not_run':['actual_xypm_transaction_producer','power_loss','sector_tearing']};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_journal_recovery_') as temp:
            root=Path(temp);boot=root/'boot.img';shutil.copyfile(image,boot)
            cases=('rollback','partial_rollback','committed','commit_moved','commit_orphan','unpublished','unpublished_bad','corrupt_journal','corrupt_commit','changed_target','corrupt_backup')
            for case in cases:
                folder=root/case;folder.mkdir();disk=folder/'work.img';create_fat32(disk,512)
                rows=[{'path':'/usr/share/p2/changed','old':b'old contents','new':b'new contents'},
                      {'path':'/usr/share/p2/removed','old':b'removed original','new':None},
                      {'path':'/usr/share/p2/newdir/newfile','old':None,'new':b'new file'}]
                journal,rows,digest=journal_bytes(rows,['/usr/share/p2/newdir'])
                commit=b'XYPCMT1\0'+digest;commit+=hashlib.sha256(commit).digest()
                if case=='corrupt_journal':journal=journal[:24]+bytes([journal[24]^1])+journal[25:]
                def temp_file(name,body):
                    path=folder/name;path.write_bytes(body);return path
                with Disk(disk,folder) as backend:
                    paths=['/var','/var/lib','/var/lib/xypm','/usr','/usr/share','/usr/share/p2','/out']
                    if case!='commit_orphan':paths+=['/var/lib/xypm/txdata','/var/lib/xypm/txdata/old','/var/lib/xypm/txdata/new']
                    if case not in ('unpublished','unpublished_bad'):paths+=['/usr/share/p2/newdir']
                    for path in paths:
                        backend.command('mkdir',path)
                    if case not in ('commit_orphan','unpublished','unpublished_bad'):
                        backend.command('import','/var/lib/xypm/transaction',temp_file('journal',journal))
                    if case in ('unpublished','unpublished_bad'):
                        backend.command('import','/var/lib/xypm/txdata/prepare',temp_file('prepare',b'XYPPRE1\0'))
                        backend.command('import','/var/lib/xypm/txdata/new/00000000',temp_file('partial',b'partial stage'))
                        if case=='unpublished_bad':backend.command('import','/var/lib/xypm/txdata/applying',temp_file('applying',b'XYPAPP1\0'))
                    for index,row in enumerate(rows):
                        old,new=row.get('old'),row.get('new');target=old if case in ('unpublished','unpublished_bad') else new
                        if case=='partial_rollback' and row['path'].endswith('/changed'):target=old
                        if case=='changed_target' and row['path'].endswith('/changed'):target=b'unknown user data'
                        if target is not None:backend.command('import',row['path'],temp_file('target_'+str(index),target))
                        if old is not None and case not in ('commit_orphan','commit_moved','unpublished','unpublished_bad') and not (case=='partial_rollback' and row['path'].endswith('/changed')):
                            backup=b'bad backup' if case=='corrupt_backup' and row['path'].endswith('/changed') else old
                            backend.command('import','/var/lib/xypm/txdata/old/%08d'%index,temp_file('old_'+str(index),backup))
                    if case=='committed':backend.command('import','/var/lib/xypm/txdata/committed',temp_file('commit',commit))
                    if case=='corrupt_commit':backend.command('import','/var/lib/xypm/txdata/committed',temp_file('commit',commit[:-1]+bytes([commit[-1]^1])))
                    if case in ('commit_moved','commit_orphan'):backend.command('import','/var/lib/xypm/transaction_commit',temp_file('commit',commit))
                guest=Guest(boot,'package_p2_recover_'+case,work_disk=disk);guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
                baseline=resources(guest);start=len(guest.output);send_bytes(guest,b'maint-recover-boot\r');guest.expect_supervisor(start=start,timeout=120)
                output=bytes(guest.output)[start:];require(resources(guest)==baseline,'resource drift in '+case)
                success=case in ('rollback','partial_rollback','committed','commit_moved','commit_orphan','unpublished')
                if success:
                    expected=b'committed transaction cleaned' if case in ('committed','commit_moved','commit_orphan') else b'unpublished preparation cleaned' if case=='unpublished' else b'transaction rolled back'
                    require(expected in output and b'maintenance: completed' in output,'recovery did not complete: '+repr(output[-2000:]))
                else:
                    require(b'materials retained' in output and b'maintenance: retained' in output,'corruption did not retain gate: '+repr(output[-2000:]))
                guest.close();(out/(case+'.log')).write_bytes(guest.output);guest=None
                with Disk(disk,folder,True) as backend:
                    if success:
                        require(backend.info('/var/lib/xypm/transaction') is None,'marker remains after '+case)
                        require(backend.info('/var/lib/xypm/txdata') is None,'transaction data remains after '+case)
                        require(backend.info('/var/lib/xypm/transaction_commit') is None,'final commit remains after '+case)
                        for row in rows:
                            expected=row.get('new') if case in ('committed','commit_moved','commit_orphan') else row.get('old');found=backend.info(row['path'])
                            if expected is None:require(found is None,'unexpected target '+row['path'])
                            else:require(found is not None and backend.export(row['path']).read_bytes()==expected,'wrong target '+row['path'])
                        if case in ('rollback','partial_rollback','unpublished'):require(backend.info('/usr/share/p2/newdir') is None,'new directory survives rollback')
                    else:
                        if case!='unpublished_bad':require(backend.info('/var/lib/xypm/transaction') is not None,'corrupt marker deleted')
                        require(backend.info('/var/lib/xypm/txdata/old') is not None,'recovery material deleted')
                        target=backend.export('/usr/share/p2/changed').read_bytes()
                        require(target==(b'unknown user data' if case=='changed_target' else b'old contents' if case=='unpublished_bad' else b'new contents'),'target changed after rejected recovery')
                report['checks'].append(case)
            report['baseline']=baseline;report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-8000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed_serial.log').write_bytes(guest.output)
        (out/'recovery_report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
