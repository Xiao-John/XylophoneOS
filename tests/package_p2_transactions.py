# SPDX-License-Identifier: Apache-2.0
"""Real guest P2 install, upgrade, removal and offline persistence."""
import argparse
import copy
import hashlib
import json
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
from process_smoke import resources
from task_smoke import send_bytes,pump
from xypm_format import canonical,load_json,require,sha_file,verify_package
from xypm_image import Disk,query_image
from package_p2_verify_guest import fixtures,make_archive


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--system',type=Path,required=True);parser.add_argument('--xypm-build',type=Path,required=True);parser.add_argument('--profile',type=Path,default=ROOT/'config/package/xos_x86_64_static_single_b2_v1.json');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    system_info=load_json(system/'manifest.json');image=system/'xos.img';require(sha_file(image)==system_info['artifacts']['xos.img']['sha256'],'system image mismatch')
    build=load_json(args.xypm_build);elf=Path(build['elf']);profile=load_json(args.profile)
    report={'status':'failed','system_build_id':system_info['build_id'],'image_sha256':sha_file(image),'xypm_elf_sha256':sha_file(elf),'xypm_package_sha256':build['sha256'],'test_sha256':sha_file(Path(__file__)),'checks':[],'not_run':['stepwise_fault_injection','power_loss','sector_tearing']};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p2_transactions_') as temp:
            root=Path(temp);fixtures(root,profile,elf);first=root/'valid.xpk';manifest=copy.deepcopy(verify_package(first,profile)['manifest'])
            with tarfile.open(first,'r') as archive:bodies={entry['path']:archive.extractfile('payload/'+entry['path']).read() for entry in manifest['files']}
            manifest['upstream_version']='1.1';manifest['revision']=1;entry=manifest['files'][0];bodies[entry['path']]=b'upgraded content\n';entry['size']=len(bodies[entry['path']]);entry['sha256']=hashlib.sha256(bodies[entry['path']]).hexdigest()
            second=root/'upgrade.xpk';make_archive(second,manifest,bodies);verify_package(second,profile)
            disk=root/'work.img';create_fat32(disk,512)
            with Disk(disk,root) as backend:
                for path in ('/usr','/usr/bin','/usr/share','/out'):backend.command('mkdir',path)
                backend.command('import','/usr/bin/xypm',elf);backend.command('import','/out/valid.xpk',first);backend.command('import','/out/upgrade.xpk',second)
                sentinel=root/'sentinel';sentinel.write_bytes(b'user data');backend.command('import','/out/sentinel',sentinel)
            boot=root/'boot.img';shutil.copyfile(image,boot)
            def start():
                g=Guest(boot,'package_p2_transactions',work_disk=disk);g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=40);pump(g,1.5);return g
            guest=start();baseline=resources(guest);report['baseline']=baseline
            def command(line,expected,timeout=300):
                begin=len(guest.output);send_bytes(guest,line.encode()+b'\r');guest.expect(expected,start=begin,timeout=timeout);guest.expect_supervisor(start=begin,timeout=timeout);data=bytes(guest.output)[begin:];require(resources(guest)==baseline,'resources drift after '+line);return data
            command('xypm install /out/valid.xpk',b'maintenance write lease required');report['checks'].append('ordinary_install_denied')
            data=command('maint-run /usr/bin/xypm install /out/valid.xpk --sha256 '+'0'*64,b'maintenance: retained');require(b'package SHA-256 mismatch' in data,'wrong expected digest not rejected')
            command('maint-recover /usr/bin/xypm recover',b'maintenance: completed');report['checks'].append('expected_hash_mismatch_rejected_before_mutation_and_xypm_recovery')
            data=command('maint-run /usr/bin/xypm install /out/valid.xpk --sha256 '+sha_file(first),b'maintenance: completed');require(b'committed transaction cleaned' in data,'install did not finish recovery cleanup');report['checks'].append('guest_install_and_cleanup')
            command('xypm info friends.p2',b'friends.p2');guest.close();(out/'install.log').write_bytes(guest.output);guest=None
            require(query_image(disk,profile,'verify-installed')['files']==3,'host cannot verify guest install')
            guest=start();baseline=resources(guest);command('xypm info friends.p2',b'friends.p2');report['checks'].append('install_survives_reboot')
            data=command('maint-run /usr/bin/xypm upgrade /out/upgrade.xpk',b'maintenance: completed');require(b'committed transaction cleaned' in data,'upgrade did not finish recovery cleanup');report['checks'].append('guest_upgrade_and_cleanup')
            guest.close();(out/'upgrade.log').write_bytes(guest.output);guest=None
            require(query_image(disk,profile,'verify-installed')['files']==3,'host cannot verify guest upgrade')
            with Disk(disk,root,True) as backend:require(backend.export('/usr/share/p2/data.txt').read_bytes()==b'upgraded content\n','upgrade content differs')
            guest=start();baseline=resources(guest);command('xypm info friends.p2',b'version: 1.1')
            data=command('maint-run /usr/bin/xypm remove friends.p2',b'maintenance: completed');require(b'committed transaction cleaned' in data,'remove did not finish recovery cleanup');report['checks'].append('guest_remove_and_cleanup')
            guest.close();(out/'remove.log').write_bytes(guest.output);guest=None
            require(query_image(disk,profile,'list')['packages']==[],'database not empty after remove')
            with Disk(disk,root,True) as backend:
                require(backend.info('/usr/share/p2/data.txt') is None,'removed package file remains')
                require(backend.info('/usr/share/p2') is None,'empty owned directory remains')
                require(backend.export('/out/sentinel').read_bytes()==b'user data','user data changed')
                require(backend.info('/var/lib/xypm/transaction') is None and backend.info('/var/lib/xypm/txdata') is None,'transaction material remains')
            report['checks'].append('remove_persists_and_empty_owned_directory_removed')
            guest=start();baseline=resources(guest);command('maint-run /usr/bin/xypm install /out/valid.xpk',b'maintenance: completed')
            guest.close();(out/'reinstall.log').write_bytes(guest.output);guest=None
            with Disk(disk,root) as backend:
                user_file=root/'user_file';user_file.write_bytes(b'user-owned data')
                backend.command('import','/usr/share/p2/user.txt',user_file)
            guest=start();baseline=resources(guest);command('maint-run /usr/bin/xypm remove friends.p2',b'maintenance: completed')
            guest.close();(out/'remove_with_user.log').write_bytes(guest.output);guest=None
            with Disk(disk,root,True) as backend:
                require(backend.export('/usr/share/p2/user.txt').read_bytes()==b'user-owned data','package-directory user file changed')
                require(backend.info('/usr/share/p2/data.txt') is None,'package file survived removal')
                require(backend.export('/out/sentinel').read_bytes()==b'user data','unrelated user data changed')
            require(query_image(disk,profile,'list')['packages']==[],'database not empty after user-file case')
            report['checks'].append('nonempty_owned_directory_and_user_data_preserved');report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'transaction_report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
