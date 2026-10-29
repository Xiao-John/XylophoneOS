#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Matched baseline/Aurora scenes in the same guest ELF; sampled memory only."""
import argparse,hashlib,json,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','image_sha256':sha(a.image),'elf_sha256':sha(a.payload),'runs':[],'absolute_peak':'NOT_RUN'};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_aurora_memory_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/memory.elf',a.payload)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command;g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);command(g,'display-start',b'result=0');g.expect(b'[display-service] ready');base=resources(g)
  for i in range(3):
   pair={}
   for mode in ('baseline','aurora'):
    result=command(g,'exec-file /bin/memory.elf '+mode,b'kind=exited code=0',timeout=90);m=re.search(rb'WIDGETS_MEMORY mode=\w+ pages=(\d+) threads=(\d+)',result);assert m;pair[mode]=int(m[1]);pair[mode+'_threads']=int(m[2]);assert 2<=int(m[2])<=4;assert resources(g)==base
   pair['additional_sampled_bytes']=(pair['aurora']-pair['baseline'])*4096;report['runs'].append(pair)
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
