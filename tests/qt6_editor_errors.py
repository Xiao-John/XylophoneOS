#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real PS/2 save actions expose FAT read-only/full failures in the Aurora editor."""
import argparse,hashlib,json,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from qt6_fat_fixture import alter
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','elf_sha256':sha(a.payload),'image_sha256':sha(a.image),'checks':[]};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_editor_errors_') as tmp:
  tmp=Path(tmp);original=tmp/'original';original.write_bytes(b'Original file must survive.\n')
  for mode,marker in [('readonly',b'Target is not writable'),('full',b'Cannot stage save')]:
   disk=tmp/(mode+'.img');create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/notes.elf',a.payload);transfer(disk,'import','/LOCK.TXT',original);alter(disk,mode)
   g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/'+mode,work_disk=disk);g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);command(g,'display-start',b'result=0');g.expect(b'[display-service] ready');base=resources(g)
   b=len(g.output);send_bytes(g,b'spawn-file /bin/notes.elf /LOCK.TXT\r');g.expect(b'QT_EDITOR_READY',start=b,timeout=90);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1])
   def key(k,d):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':d,'key':{'type':'qcode','data':k}}}]})
   key('a',True);key('a',False);key('ctrl',True);key('s',True);key('s',False);key('ctrl',False);g.expect(marker,start=b,timeout=30);assert b'EDITOR_SAVE_OK' not in bytes(g.output)[b:]
   g.qmp('screendump',{'filename':str(out/(mode+'.ppm'))});from PIL import Image
   Image.open(out/(mode+'.ppm')).save(out/(mode+'.png'))
   command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed');assert resources(g)==base;command(g,'sync',b'[files] sync=ok');(out/(mode+'.serial.log')).write_bytes(g.output);cmd=g.command;g.close();g=None
   exported=tmp/(mode+'.bytes');transfer(disk,'export','/LOCK.TXT',exported);assert exported.read_bytes()==original.read_bytes()
   report['checks'].append({'mode':mode,'status':'PASSED','original_sha256':sha(exported),'resources':base,'qemu_command':cmd})
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'failed.serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
