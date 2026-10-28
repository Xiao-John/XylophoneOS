# SPDX-License-Identifier: Apache-2.0
"""Exercise guest upgrade on a nearly full FAT disk and verify recovery."""
import argparse, copy, hashlib, json, shutil, sys, tarfile, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes, pump
from xypm_format import canonical,load_json,require,sha_file,verify_package
from xypm_image import Disk,query_image,transact
from package_p2_verify_guest import fixtures,make_archive

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--system',type=Path,required=True);p.add_argument('--xypm-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);system=a.system.resolve();info=load_json(system/'manifest.json');image=system/'xos.img';require(sha_file(image)==info['artifacts']['xos.img']['sha256'],'system image mismatch');build=load_json(a.xypm_build);elf=Path(build['elf']);profile=load_json(ROOT/'config/package/xos_x86_64_static_single_b2_v1.json');guest=None
    report={'status':'failed','system_build_id':info['build_id'],'image_sha256':sha_file(image),'xypm_elf_sha256':sha_file(elf),'test_sha256':sha_file(Path(__file__)),'checks':[],'not_run':['power_loss','sector_tearing']}
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p2_full_') as temp:
            root=Path(temp);fixtures(root,profile,elf);first=root/'valid.xpk';manifest=copy.deepcopy(verify_package(first,profile)['manifest'])
            with tarfile.open(first,'r') as archive:bodies={entry['path']:archive.extractfile('payload/'+entry['path']).read() for entry in manifest['files']}
            manifest['upstream_version']='1.1';manifest['revision']=1;entry=manifest['files'][0];bodies[entry['path']]=b'new content\n';entry['size']=len(bodies[entry['path']]);entry['sha256']=hashlib.sha256(bodies[entry['path']]).hexdigest();second=root/'upgrade.xpk';make_archive(second,manifest,bodies);verify_package(second,profile)
            base=root/'base.img';create_fat32(base,512)
            with Disk(base,root) as disk:
                for path in ('/usr','/usr/bin','/usr/share','/out'):disk.command('mkdir',path)
                disk.command('import','/usr/bin/xypm',elf);disk.command('import','/out/upgrade.xpk',second)
                sentinel=root/'sentinel';sentinel.write_bytes(b'user data');disk.command('import','/out/sentinel',sentinel)
            work=root/'work.img';transact(base,work,profile,'install',package=first)
            with Disk(work,root) as disk:
                free=disk.command('free');available,cluster=int(free[1]),int(free[2]);filler=root/'filler';filler.touch();
                with filler.open('r+b') as f:f.truncate(available-1024*1024)
                disk.command('import','/out/filler',filler);after=disk.command('free');report['free_before']=available;report['free_after']=int(after[1]);report['cluster_bytes']=cluster
            boot=root/'boot.img';shutil.copyfile(image,boot);guest=Guest(boot,'package_p2_full_disk',work_disk=work);guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1)
            start=len(guest.output);send_bytes(guest,b'demo quiet\r');guest.expect_any((b'demo tasks stopped',b'demo tasks already stopped'),start=start,timeout=40);guest.expect_supervisor(start=start,timeout=40)
            start=len(guest.output);send_bytes(guest,b'maint-run /usr/bin/xypm upgrade /out/upgrade.xpk\r');guest.expect(b'maintenance: retained',start=start,timeout=300);guest.expect_supervisor(start=start,timeout=60);require(b'transaction stopped' in bytes(guest.output)[start:],'full disk did not stop transaction');report['checks'].append('full_disk_upgrade_stopped')
            start=len(guest.output);send_bytes(guest,b'maint-recover-boot\r');guest.expect(b'maintenance: completed',start=start,timeout=120);guest.expect_supervisor(start=start,timeout=60);guest.close();(out/'guest.log').write_bytes(guest.output);guest=None
            listed=query_image(work,profile,'list')['packages'];query_image(work,profile,'verify-installed');require(len(listed)==1 and listed[0]['upstream_version']=='1.0','old package changed')
            with Disk(work,root,True) as disk:
                require(disk.export('/out/sentinel').read_bytes()==b'user data','user file changed')
                for path in ('/var/lib/xypm/transaction','/var/lib/xypm/txdata','/var/lib/xypm/transaction_commit'):require(disk.info(path) is None,'transaction residue: '+path)
            report['checks'].append('recovery_preserves_installed_package_and_user_data');report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'full_disk_report.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
