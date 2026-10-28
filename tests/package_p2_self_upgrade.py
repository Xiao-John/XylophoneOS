# SPDX-License-Identifier: Apache-2.0
"""Recover the package manager from immutable boot media during self-upgrade."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes,pump
from xypm_format import canonical,load_json,require,sha_file
from xypm_image import Disk,query_image,transact
from package_p2_faults import sparse_copy


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--system',type=Path,required=True);parser.add_argument('--build',type=Path,required=True);parser.add_argument('--fault-build',type=Path,required=True);parser.add_argument('--profile',type=Path,default=ROOT/'config/package/xos_x86_64_static_single_b2_v1.json');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);system_info=load_json(system/'manifest.json');image=system/'xos.img';require(sha_file(image)==system_info['artifacts']['xos.img']['sha256'],'system image mismatch');normal=load_json(args.build);fault=load_json(args.fault_build);profile=load_json(args.profile)
    report={'status':'failed','system_build_id':system_info['build_id'],'image_sha256':sha_file(image),'normal_package_sha256':normal['sha256'],'fault_package_sha256':fault['sha256'],'test_sha256':sha_file(Path(__file__)),'checks':[],'not_run':['power_loss','sector_tearing']};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_self_upgrade_') as temp:
            root=Path(temp);source=root/'source.img';create_fat32(source,512)
            with Disk(source,root) as disk:
                disk.command('mkdir','/out');disk.command('import','/out/new.xpk',normal['package'])
                sentinel=root/'sentinel';sentinel.write_bytes(b'user data');disk.command('import','/out/sentinel',sentinel)
            base=root/'base.img';transact(source,base,profile,'install',package=fault['package'])
            boot=root/'boot.img';shutil.copyfile(image,boot)
            def start(disk):
                g=Guest(boot,'package_p2_self_upgrade',work_disk=disk);g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=40);pump(g,1.0)
                if b'maintenance: persistent recovery required' not in g.output:
                    begin=len(g.output);send_bytes(g,b'demo quiet\r');g.expect_any((b'demo tasks stopped',b'demo tasks already stopped'),start=begin,timeout=40);g.expect_supervisor(start=begin,timeout=40)
                return g
            def command(g,line,expected,timeout=600):
                begin=len(g.output);send_bytes(g,line.encode()+b'\r');match=g.expect_any((expected,b'xsh> '),start=begin,timeout=timeout);require(match==expected,'unexpected result for '+line+': '+repr(bytes(g.output)[begin:][-3000:]));g.expect_supervisor(start=begin,timeout=timeout);return bytes(g.output)[begin:]
            probe=root/'probe.img';sparse_copy(base,probe);guest=start(probe);baseline=resources(guest)
            output=command(guest,'maint-run /usr/bin/xypm upgrade /out/new.xpk',b'maintenance: completed')
            found=re.search(rb'xypm-test: self_removed=(\d+)',output);require(found,'no self-removal checkpoint');step=int(found.group(1));require(resources(guest)==baseline,'resources drift after normal upgrade');guest.close();(out/'normal.log').write_bytes(guest.output);guest=None
            require(query_image(probe,profile,'verify-installed')['files']==normal['files'],'upgraded package fails verification')
            require(query_image(probe,profile,'info','xos.xypm')['sha256']==normal['sha256'],'normal self-upgrade database differs');report['checks'].append('normal_self_upgrade')
            trial=root/'trial.img';sparse_copy(base,trial);guest=start(trial);baseline=resources(guest)
            output=command(guest,'maint-run /usr/bin/xypm upgrade /out/new.xpk --fault-after '+str(step),b'maintenance: retained')
            require(('xypm-test: injected='+str(step)).encode() in output,'self-removal interruption not reached');require(resources(guest)==baseline,'resources drift after interrupt');guest.close();(out/'interrupted.log').write_bytes(guest.output);guest=None
            with Disk(trial,root,True) as disk:
                require(disk.info('/usr/bin/xypm') is None,'xypm executable was not absent at interruption')
                require(disk.info('/var/lib/xypm/transaction') is not None,'journal missing at interruption')
            guest=start(trial);baseline=resources(guest);output=command(guest,'maint-recover-boot',b'maintenance: completed');require(b'transaction rolled back' in output,'boot recovery did not roll back');require(resources(guest)==baseline,'resources drift after recovery');guest.close();(out/'recovered.log').write_bytes(guest.output);guest=None
            require(query_image(trial,profile,'verify-installed')['files']==fault['files'],'restored package fails verification')
            require(query_image(trial,profile,'info','xos.xypm')['sha256']==fault['sha256'],'restored database differs')
            with Disk(trial,root,True) as disk:
                require(sha_file(disk.export('/usr/bin/xypm'))==sha_file(Path(fault['elf'])),'original xypm binary not restored')
                require(disk.export('/out/sentinel').read_bytes()==b'user data','user data changed')
            report['checks'].append('boot_recovery_restores_missing_xypm');report['self_removal_checkpoint']=step
            guest=start(trial);baseline=resources(guest);command(guest,'maint-run /usr/bin/xypm upgrade /out/new.xpk',b'maintenance: completed');require(resources(guest)==baseline,'resources drift after retry');guest.close();(out/'retry.log').write_bytes(guest.output);guest=None
            require(query_image(trial,profile,'verify-installed')['files']==normal['files'],'retry upgrade failed host verification');report['checks'].append('self_upgrade_retry');report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'self_upgrade_report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
