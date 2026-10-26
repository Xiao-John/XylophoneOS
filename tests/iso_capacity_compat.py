# SPDX-License-Identifier: Apache-2.0
"""Normal kernel compatibility after the large-ISO path changes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from task_smoke import send_bytes
from make_work_disk import create_fat32
from xypm_image import Disk
from xypm_format import sha_file


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,default=ROOT/'build/iso_capacity/normal')
    parser.add_argument('--dash-manifest',type=Path,default=ROOT/'.cache/xos_seed/dash/8098a3cc28ff4ce74f5b/manifest.json')
    parser.add_argument('--output',type=Path,required=True,help='new private output directory')
    args=parser.parse_args();build=args.build_dir.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    dash=args.dash_manifest.resolve();system=json.loads((build/'manifest.json').read_text())
    assert system['legacy_images_available'] and not system['capacity_probe']
    for name in ('xos.img','xos.iso'):
        assert sha_file(build/name)==system['artifacts'][name]['sha256']
    subprocess.run([sys.executable,str(ROOT/'scripts/build_install_iso.py'),'--build-dir',str(build),
                    '--dash-manifest',str(dash),'--output',str(out/'install.iso'),
                    '--manifest',str(out/'manifest.json')],check=True)
    report={'status':'failed','build_id':system['build_id'],'checks':[]}
    try:
        for name,image,iso in [('floppy',build/'xos.img',False),('embedded_iso',build/'xos.iso',True),
                               ('file_iso',out/'install.iso',True)]:
            disk=out/(name+'.img');create_fat32(disk,512)
            guest=Guest(image,'iso_capacity/'+name,iso=iso,work_disk=disk)
            try:
                guest.expect(b'xos64> ',timeout=35)
                start=len(guest.output);send_bytes(guest,b'run\r');guest.expect_supervisor(start=start,timeout=45)
                if name=='file_iso':
                    guest.expect(b'[files] dash installed bytes=',start=start,timeout=45)
                    start=len(guest.output);send_bytes(guest,b'dash -i\r');guest.expect(b'$ ',start=start,timeout=35)
                    start=len(guest.output);send_bytes(guest,b'exit\r');guest.expect_supervisor(start=start,timeout=35)
                    start=len(guest.output);send_bytes(guest,b'sync\r');guest.expect(b'[files] sync=ok',start=start)
                    guest.expect_supervisor(start=start)
                assert b'[panic]' not in guest.output
                report['checks'].append(name+'_normal_kernel_boot_and_files')
            finally:guest.close()
            if name=='file_iso':
                with Disk(disk,out,True) as volume:
                    assert sha_file(volume.export('/usr/bin/dash'))==json.loads(dash.read_text())['sha256']
                report['checks'].append('normal_dash_payload_full_hash')
        report['status']='passed'
    finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
