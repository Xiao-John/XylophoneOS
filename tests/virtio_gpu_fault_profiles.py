#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real device host quota, kernel DMA quota, queue timeout, fallback and no-device."""
import argparse,hashlib,json,re,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
p=argparse.ArgumentParser()
for n in ('default-system','quota-system','timeout-system','qt-payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();g=None
receipt=json.loads(a.qt_payload.with_suffix('.receipt.json').read_text());assert sha(a.qt_payload)==receipt['elf_sha256']
for n,h in receipt['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','elf_sha256':sha(a.qt_payload),'receipt_sha256':sha(a.qt_payload.with_suffix('.receipt.json')),'checks':[]}
try:
 with tempfile.TemporaryDirectory(prefix='xos_vgpu_faults_') as tmp:
  tmp=Path(tmp)
  cases=[('host_quota',a.default_system,'none','virtio-gpu-pci,id=vgpu,disable-legacy=on,max_hostmem=2097152'),('host_init_quota',a.default_system,'std','virtio-gpu-pci,id=vgpu,disable-legacy=on,max_hostmem=1048576'),('dma_quota',a.quota_system,'std','virtio-gpu-pci,id=vgpu,disable-legacy=on'),('timeout',a.timeout_system,'std','virtio-gpu-pci,id=vgpu,disable-legacy=on'),('no_device',a.default_system,'none',None)]
  for name,system,vga,device in cases:
   manifest=json.loads((system/'manifest.json').read_text());assert sha(system/'xos.img')==manifest['artifacts']['xos.img']['sha256']
   disk=tmp/(name+'.img');create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/gui.elf',a.qt_payload)
   original=boot_smoke.qemu_command
   def qemu(*args,**kw):
    cmd=original(*args,**kw);cmd[cmd.index('-vga')+1]=vga
    if device:cmd+=['-device',device]
    return cmd
   with patch.object(boot_smoke,'qemu_command',qemu):g=Guest((system/'xos.img').resolve(),str(out.relative_to(ROOT/'build'))+'/'+name,work_disk=disk)
   g.expect(b'xos64> ',timeout=45)
   if name=='host_quota':
    send_bytes(g,b'gpu-quota-test\r');g.expect(b'gpu-quota-test pass',timeout=30);assert b'0x0000000000001201' in g.output
   elif name!='no_device':
    assert b'[display] backend=vbe fallback=1' in g.output and b'[display] backend=virtio-gpu-2d' not in g.output
    expected={'host_init_quota':b'resource_init_failed','dma_quota':b'queue_init_failed','timeout':b'queue_timeout'}[name];assert expected in g.output
    freed=re.search(rb'DMA_released=(\d+) free_before=(\d+) free_after=(\d+)',g.output);assert freed and int(freed[3])-int(freed[2])==int(freed[1]),g.output[-1000:]
   send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);base=resources(g)
   if name=='no_device':
    result=command(g,'exec-file /bin/gui.elf auto',b'kind=exited',timeout=90);assert b'unavailable or invalid Display Service mode (-19)' in result;assert resources(g)==base
   else:
    result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',result)[1]);g.expect(b'[display-service] ready');with_service=resources(g)
    result=command(g,'exec-file /bin/gui.elf auto',b'kind=exited code=0',timeout=90);assert b'QT_GUI_OK' in result;assert resources(g)==with_service
    command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base
   report['checks'].append({'name':name,'status':'PASSED','image_sha256':sha(system/'xos.img'),'build_id':manifest['build_id'],'configuration':manifest.get('virtio_gpu'),'resources':base,'qemu_command':g.command})
   (out/(name+'.serial.log')).write_bytes(g.output);g.close();g=None;print(name,'PASSED',flush=True)
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'failed.serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
