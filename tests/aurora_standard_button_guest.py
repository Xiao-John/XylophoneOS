#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render ordinary Qt controls using the XOS guest and capture actual scanout."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command,resources
from task_smoke import pump,send_bytes
from work_disk import transfer

p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--dash',type=Path)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
receipt=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert receipt['elf_sha256']==sha(a.payload)
for name,digest in receipt['inputs'].items():assert sha(Path(name))==digest,name
report={'status':'FAILED','image_sha256':sha(a.image),'payload_sha256':sha(a.payload)};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_standard_button_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/standard.elf',a.payload)
  if a.dash:
   transfer(disk,'import','/bin/dash',a.dash);script=Path(tmp)/'standard-dash.sh'
   script.write_text('/bin/standard.elf\necho AURORA_STANDARD_DASH_STATUS:$?\n');transfer(disk,'import','/standard-dash.sh',script)
   report['dash_sha256']=sha(a.dash)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=45)
  command(g,'demo quiet',b'demo tasks stopped',timeout=20);base=resources(g);report['baseline_resources']=base
  service_data=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',service_data)[1]);g.expect(b'[display-service] ready');active=resources(g)
  start=len(g.output);send_bytes(g,b'exec-file /bin/standard.elf\r');g.expect(b'AURORA_STANDARD_READY failures=',start=start,timeout=90);pump(g,.5)
  data=bytes(g.output)[start:];checks=re.findall(rb'AURORA_STANDARD_CHECK ([a-z_]+)=(PASS|FAIL)',data)
  report['checks']=[{'name':name.decode(),'status':status.decode()} for name,status in checks]
  g.qmp('screendump',{'filename':str(out/'scanout.ppm')})
  from PIL import Image
  Image.open(out/'scanout.ppm').save(out/'scanout.png');report['screenshot_sha256']=sha(out/'scanout.png')
  for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':'esc'}}}]})
  g.expect(b'kind=exited code=0',start=start,timeout=30);g.expect_supervisor(start=start,timeout=30);assert resources(g)==active
  if a.dash:
   start=len(g.output);send_bytes(g,b'exec-driver /bin/dash /standard-dash.sh\r');g.expect(b'AURORA_STANDARD_READY failures=0',start=start,timeout=90)
   data=bytes(g.output)[start:];dash_checks=re.findall(rb'AURORA_STANDARD_CHECK ([a-z_]+)=(PASS|FAIL)',data)
   assert len(dash_checks)==3 and all(status==b'PASS' for _,status in dash_checks)
   for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':'esc'}}}]})
   g.expect(b'AURORA_STANDARD_DASH_STATUS:0',start=start,timeout=30);g.expect_supervisor(start=start,timeout=30);assert resources(g)==active
   report['dash_checks']=[{'name':name.decode(),'status':status.decode()} for name,status in dash_checks]
  command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');report['after_resources']=resources(g);assert report['after_resources']==base
  report['status']='PASSED' if len(checks)==3 and all(status==b'PASS' for _,status in checks) else 'FAILED'
except Exception as error:
 report['error']=repr(error);raise
finally:
 if g:g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status']);sys.exit(0 if report['status']=='PASSED' else 1)
