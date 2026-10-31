#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real prewired consumer reads a synthetic long Notes document in ranges."""
import argparse, base64, hashlib, json, re, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from ssg_public_paths import portable
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes, pump
p=argparse.ArgumentParser()
for name in ('image','session','consumer','notes','output'): p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args(); out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda b:hashlib.sha256(b).hexdigest()
report={'status':'FAILED','inputs':{n:{'path':str(getattr(a,n).resolve()),'sha256':sha(getattr(a,n).read_bytes())} for n in ('image','session','consumer','notes')},'checks':[]}
g=None;disk=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_ssg_range_') as td:
  tmp=Path(td); disk=tmp/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin')
  for src,name in ((a.session,'session'),(a.consumer,'ssg-consumer'),(a.notes,'notes')):transfer(disk,'import','/bin/'+name+'.elf',src)
  source='Long synthetic text 😀\n'+''.join(f'{i:04d} Alpha 😀 Omega\n' for i in range(180))
  note=tmp/'long.txt';note.write_text(source,encoding='utf-8');transfer(disk,'import','/long.txt',note)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=45)
  command(g,'demo quiet',b'demo tasks stopped');base=resources(g)
  command(g,'display-start',b'result=0');g.expect(b'[display-service] ready');active=resources(g)
  start=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /long.txt text-range --text\r')
  g.expect(b'SSG_TEXT_RANGE_COMPLETE',start=start,timeout=180);g.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=0',start=start,timeout=90)
  output=bytes(g.output)[start:];frames=[]
  for seq,size,encoded_size in re.findall(rb'SSG_FRAME_BEGIN RESP (\d+) (\d+) (\d+)',output):
   parts={int(i):v for i,v in re.findall(rb'SSG_FRAME_PART RESP '+seq+rb' (\d+) ([A-Za-z0-9+/=]+)',output)}
   raw=base64.b64decode(b''.join(parts[i] for i in sorted(parts)),validate=True)
   assert len(raw)==int(size) and len(base64.b64encode(raw))==int(encoded_size)
   frames.append(json.loads(raw));(out/(seq.decode()+'-resp.json')).write_bytes(raw)
  chunks=frames[1:];assert len(chunks)>2 and ''.join(c['text'] for c in chunks)==source
  assert all(c['sourceEpoch']==chunks[0]['sourceEpoch'] and c['documentRevision']==chunks[0]['documentRevision'] for c in chunks)
  assert chunks[-1]['remaining']==0 and chunks[-1]['end']==len(source.encode('utf-16-le'))//2
  report['checks'].append('long_unicode_range_exact_reconstruction');report['pages']=[{'start':c['start'],'end':c['end'],'revision':c['documentRevision']} for c in chunks]
  g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':True,'key':{'type':'qcode','data':'esc'}}},{'type':'key','data':{'down':False,'key':{'type':'qcode','data':'esc'}}}]})
  g.expect(b'SSG_SESSION provider_wait=',start=start,timeout=60);g.expect_supervisor(start=start,timeout=60);report['resources_before']=active;report['resources_after']=resources(g);assert report['resources_after']==active
  report['checks'].append('provider_consumer_resources_reclaimed');report['status']='PASSED'
finally:
 if g:
  (out/'serial.log').write_bytes(bytes(g.output));g.close()
 report['qemu_command_kind']='template; the runner creates the work disk and QMP socket'
 mappings=[('XOS_IMAGE',a.image),('XOS_TEST_OUT',out),('XOS_SESSION_ELF',a.session),('XOS_CONSUMER_ELF',a.consumer),('XOS_NOTES_ELF',a.notes),('XOS_WORK_DISK',disk),('XOS_QMP_SOCKET',g.qmp_path if g else None),('XOS_QEMU',g.command[0] if g else None)]
 (out/'report.json').write_text(json.dumps(portable(report,mappings,strict=True),indent=2)+'\n')
