# SPDX-License-Identifier: Apache-2.0
"""Verify a packaged release disk on an isolated copy, without rebuilding XOS."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command


def main():
    release = ROOT/'build/releases/0.0.1-1024'
    images = release/'xylophoneos_revival_0.0.1-1024_images'
    report = {'status':'failed', 'checks':[], 'build_id':'2c3876e640840ff5'}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_release_') as folder:
            disk = Path(folder)/'work.img'
            subprocess.run(['cp','-c',str(images/'work_disk.img'),str(disk)],check=True)
            for kind in ('c','cpp'):
                subprocess.run([str(ROOT/'build/work_disk_host'),str(disk),'import',
                                '/out/sdk_'+kind+'.elf',str(release/('sdk_'+kind+'.elf'))],check=True)
            guest = Guest(images/'xos.img','release_package',work_disk=disk)
            guest.expect(b'xos64> ',timeout=40)
            send_bytes(guest,b'run\r');guest.expect(b'sup> ',timeout=40);pump(guest,1.5)
            for kind, compiler in (('c','gcc'),('cpp','g++')):
                command(guest,'exec-driver /usr/bin/x86_64-elf-'+compiler+
                        ' -static --sysroot=/sysroot /src/hello.'+kind+' -o /out/hello_'+kind+'.elf',
                        b'kind=exited code=0',timeout=180)
                command(guest,'exec-file /out/hello_'+kind+'.elf',
                        b'Happy 1024 from XOS C'+(b'++!' if kind=='cpp' else b'!'),timeout=45)
                report['checks'].append('packaged_native_'+kind)
                command(guest,'exec-file /out/sdk_'+kind+'.elf',
                        b'Happy 1024 from XOS C'+(b'++!' if kind=='cpp' else b'!'),timeout=45)
                report['checks'].append('packaged_sdk_'+kind)
            command(guest,'sync',b'[files] sync=ok',timeout=30)
            report['status']='passed'
    finally:
        if guest:guest.close()
        (release/'package_smoke_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
