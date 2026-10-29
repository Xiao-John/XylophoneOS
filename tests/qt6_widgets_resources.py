#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual Widgets OOM/thread quota/client fault/service-present fault recovery."""
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
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','elf_sha256':sha(a.payload),'image_sha256':sha(a.image),'checks':[]};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_widgets_resources_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/resources.elf',a.payload)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command;g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);base=resources(g)
  result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',result)[1]);g.expect(b'[display-service] ready');with_service=resources(g)
  for mode,marker in [('oom',b'WIDGETS_OOM_NULL'),('quota',b'input thread resource allocation failed'),('fault',b'kind=faulted')]:
   result=command(g,'exec-file /bin/resources.elf '+mode,b'kind=faulted' if mode=='fault' else b'kind=exited',timeout=90);assert marker in result,result[-1800:];assert resources(g)==with_service;report['checks'].append({'name':mode,'status':'PASSED','resources':with_service})
  command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base
  result=command(g,'display-start fault',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',result)[1]);result=command(g,'exec-file /bin/resources.elf oom',b'kind=exited code=72',timeout=90)
  assert b'present failed (-19)' in result or b'Display Service disconnected' in result
  command(g,f'wait {service}',b'kind=faulted');assert resources(g)==base;report['checks'].append({'name':'display_service_fault_in_present','status':'PASSED','resources':base});report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
