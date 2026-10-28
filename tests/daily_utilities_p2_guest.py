# SPDX-License-Identifier: Apache-2.0
"""Install daily XPK with guest xypm P2, reboot, use, and remove on a private disk."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import pump, send_bytes
from xypm_format import load_json, require, sha_file, verify_package
from xypm_image import Disk, query_image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',type=Path,required=True); parser.add_argument('--xypm-build',type=Path,required=True)
    parser.add_argument('--package',type=Path,required=True); parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--dash',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    system=load_json(args.system/'manifest.json'); image=args.system/'xos.img'; profile=load_json(args.profile)
    build=load_json(args.xypm_build); elf=Path(build['elf']); package=verify_package(args.package,profile)
    require(sha_file(image)==system['artifacts']['xos.img']['sha256'],'system mismatch')
    require(package['manifest']['id']=='xos.daily_utilities','wrong package')
    report={'status':'failed','system_build_id':system['build_id'],'image_sha256':sha_file(image),
            'xypm_elf_sha256':sha_file(elf),'package_sha256':sha_file(args.package),
            'profile_sha256':sha_file(args.profile),'dash_sha256':sha_file(args.dash), 'checks':[],
            'not_run':['fault_injection','abrupt_power_loss','upgrade','iso_install']};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_du_p2_') as tmp:
            root=Path(tmp);disk=root/'work.img';create_fat32(disk,512)
            with Disk(disk,root) as backend:
                for path in ('/usr','/usr/bin','/out','/tmp','/tests'):backend.command('mkdir',path)
                backend.command('import','/usr/bin/xypm',elf)
                backend.command('import','/usr/bin/dash',args.dash)
                backend.command('import','/out/daily.xpk',args.package)
                backend.command('import','/tests/du12.sh',ROOT/'tests/fixtures/daily_utilities/du12.sh')
                backend.command('import','/tests/binary.dat',ROOT/'tests/fixtures/daily_utilities/binary.dat')
            def boot():
                g=Guest(image,'daily_p2',work_disk=disk);g.expect(b'xos64> ',timeout=40)
                send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=40);pump(g,1.5);return g
            def command(g,line,expected,timeout=360):
                start=len(g.output);send_bytes(g,line.encode()+b'\r');g.expect(expected,start=start,timeout=timeout)
                g.expect_supervisor(start=start,timeout=timeout);return bytes(g.output[start:])
            guest=boot();baseline=resources(guest);report['baseline']=baseline
            data=command(guest,'maint-run /usr/bin/xypm install /out/daily.xpk --sha256 '+sha_file(args.package),b'maintenance: completed')
            require(b'committed transaction cleaned' in data,'install cleanup missing')
            require(resources(guest)==baseline,'resources drift after install')
            report['checks'].append('guest_p2_install');guest.close();(out/'install.log').write_bytes(guest.output);guest=None
            require(query_image(disk,profile,'verify-installed')['files']==len(package['manifest']['files']),'installed contents mismatch')
            guest=boot();baseline=resources(guest)
            data=command(guest,'dash /tests/du12.sh',b'DU12_OK',timeout=180)
            require(resources(guest)==baseline,'resources drift after utilities')
            command(guest,'sync',b'xsh> ');report['checks'].append('reboot_and_installed_tools')
            data=command(guest,'maint-run /usr/bin/xypm remove xos.daily_utilities',b'maintenance: completed')
            require(b'committed transaction cleaned' in data,'remove cleanup missing')
            require(resources(guest)==baseline,'resources drift after remove')
            guest.close();(out/'run_remove.log').write_bytes(guest.output);guest=None
            require(query_image(disk,profile,'list')['packages']==[],'package remains')
            with Disk(disk,root,True) as backend:
                require(backend.info('/usr/bin/ls') is None,'managed executable remains')
                require(backend.export('/tmp/du/tail_pipe.txt').read_bytes()==b'b\nc','user data changed')
            report['checks'].append('guest_p2_remove_preserves_user_data');report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-12000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
