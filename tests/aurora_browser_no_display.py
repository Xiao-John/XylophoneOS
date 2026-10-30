#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Browser without VGA: explicit QPA failure, no resource leak, serial rescue."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','elf_sha256':sha(a.payload),'image_sha256':sha(a.image)};g=None
original=boot_smoke.qemu_command
def no_display(*args,**kw):
 c=original(*args,**kw);c[c.index('-vga')+1]='none';return c
try:
 with tempfile.TemporaryDirectory(prefix='xos_browser_none_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/aurora.elf',a.payload)
  with patch.object(boot_smoke,'qemu_command',no_display):g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk)
  report['qemu_command']=g.command;g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.2);base=resources(g)
  result=command(g,'exec-file /bin/aurora.elf',b'kind=exited',timeout=90);assert b'unavailable or invalid Display Service mode (-19)' in result;assert resources(g)==base
  command(g,'sync',b'[files] sync=ok');report.update(status='PASSED',checks=['no_display_explicit_QPA_failure','exact_resources_after_failed_browser','serial_and_file_sync_survive'],baseline=base)
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
