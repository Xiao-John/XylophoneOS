#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the minimal real QWidget/viewport probe; preserve failures and scanout."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
g=None;report={'status':'FAILED'}
receipt=json.loads(a.payload.with_suffix('.receipt.json').read_text())
assert hashlib.sha256(a.payload.read_bytes()).hexdigest()==receipt['elf_sha256']
for name,h in receipt['inputs'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
try:
 with tempfile.TemporaryDirectory(prefix='xos_widgets_probe_') as d:
  disk=Path(d)/'work.img';create_fat32(disk,512)
  transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/probe.elf',a.payload)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk)
  report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1)
  command(g,'display-start',b'result=0');g.expect(b'[display-service] ready')
  report['baseline']=resources(g)
  b=len(g.output);send_bytes(g,b'exec-file /bin/probe.elf\r')
  g.expect(b'QT_WIDGETS_READY',start=b,timeout=90)
  def key(k,down):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':k}}}]})
  key('a',True);key('a',False);g.expect(b'QT_WIDGETS_TEXT',start=b);pump(g,.3)
  g.qmp('screendump',{'filename':str(out/'widgets.ppm')})
  from PIL import Image
  Image.open(out/'widgets.ppm').save(out/'widgets.png')
  # Kill via the retained serial supervisor; following run verifies normal teardown.
  # foreground execution can be cancelled via existing Ctrl+C serial mechanism.
  key('esc',True);key('esc',False);g.expect(b'kind=exited code=0',start=b,timeout=15);g.expect_supervisor(start=b)
  result=command(g,'exec-file /bin/probe.elf auto',b'kind=exited code=0',timeout=90)
  assert b'QT_WIDGETS_OK' in result
  assert resources(g)==report['baseline']
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
