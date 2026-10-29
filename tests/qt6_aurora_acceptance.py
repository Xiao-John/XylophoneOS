#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Independent consumer of the linked Aurora library; real guest visual states."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','elf_sha256':sha(a.payload),'image_sha256':sha(a.image),'checks':[]};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_aurora_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/aurora.elf',a.payload)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);command(g,'display-start',b'result=0');g.expect(b'[display-service] ready');base=resources(g)
  b=len(g.output);send_bytes(g,b'exec-file /bin/aurora.elf\r');g.expect(b'AURORA_SHOWCASE_READY',start=b,timeout=90);pump(g,.2)
  def shot(name):
   g.qmp('screendump',{'filename':str(out/(name+'.ppm'))})
   from PIL import Image
   im=Image.open(out/(name+'.ppm'));assert im.size==(800,600);im.save(out/(name+'.png'));report.setdefault('screenshots',{})[name]=sha(out/(name+'.png'))
  shot('standard-widgets')
  from PIL import Image
  im=Image.open(out/'standard-widgets.png')
  assert sum(1 for r,g,b in im.crop((94,82,690,106)).convert('RGB').get_flattened_data() if min(r,g,b)>130)>100,'Label text contrast'
  assert sum(1 for r,g,b in im.crop((98,189,690,250)).convert('RGB').get_flattened_data() if min(r,g,b)>130)>300,'Document text contrast'
  def key(k,d):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':d,'key':{'type':'qcode','data':k}}}]})
  key('tab',True);key('tab',False);pump(g,.1);shot('keyboard-focus')
  g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-150}},{'type':'rel','data':{'axis':'y','value':-160}}]});pump(g,.3);shot('hover')
  g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':True}}]});pump(g,.1);shot('pressed')
  g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':False}}]});key('esc',True);key('esc',False)
  g.expect(b'kind=exited code=0',start=b,timeout=30);g.expect_supervisor(start=b);assert resources(g)==base
  report['checks']=['independent_linked_style_library','standard_QPushButton_QLineEdit_QPlainTextEdit_QLabel','enabled_primary_disabled_focus_hover_pressed','cached_glass_and_software_pointer','resources_exactly_restored'];report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
