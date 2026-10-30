#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual VirtIO-GPU/VBE scanout, fenced dirty updates, isolation and CPU observations."""
import argparse,hashlib,json,re,subprocess,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/final_runs/gpu_paired');sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser()
for n in ('system','qt-payload','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--access-payload',type=Path)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
image=a.system/'xos.img';manifest=json.loads((a.system/'manifest.json').read_text());assert sha(image)==manifest['artifacts']['xos.img']['sha256']
receipt=json.loads(a.qt_payload.with_suffix('.receipt.json').read_text());assert sha(a.qt_payload)==receipt['elf_sha256']
for n,h in receipt['inputs'].items():assert sha(n)==h,n
# The C branch changes kernel internals only. Verify every SDK runtime/shared input.
sdk=next(Path(n).parent for n in receipt['inputs'] if n.endswith('/sdk/manifest.json'))
sdk_manifest=json.loads((sdk/'manifest.json').read_text());checked={}
for n,h in sdk_manifest['inputs'].items():
 if n.startswith(('src/shared/','src/user/')):assert sha(Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e17')/n)==h,n;checked[n]=h
report={'status':'FAILED','build_id':manifest['build_id'],'image_sha256':sha(image),'elf_sha256':sha(a.qt_payload),'sdk_compatible_inputs':checked,'checks':[],'runs':[]};g=None

def key(k,d):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':d,'key':{'type':'qcode','data':k}}}]})
def stroke(k):key(k,True);key(k,False)
def boot(disk,backend,name):
 global g
 original=boot_smoke.qemu_command
 def qemu(*args,**kw):
  cmd=original(*args,**kw)
  if backend=='virtio':cmd[cmd.index('-vga')+1]='none';cmd+=['-device','virtio-gpu-pci,id=vgpu,disable-legacy=on']
  return cmd
 with patch.object(boot_smoke,'qemu_command',qemu):g=Guest(image.resolve(),str(out.relative_to(ROOT/'build'))+'/'+name,work_disk=disk)
 g.expect(b'xos64> ',timeout=45)
 if backend=='virtio':
  assert b'[display] backend=virtio-gpu-2d' in g.output and b'state=ready width=' not in g.output
  send_bytes(g,b'gpu-test\r');g.expect(b'gpu-test pass',timeout=30)
 else:assert b'[display] backend=vbe fallback=1' in g.output
 send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3)
def close(name):
 global g
 (out/(name+'.serial.log')).write_bytes(g.output);g.close();g=None
def cpu_seconds():
 text=subprocess.check_output(['ps','-p',str(g.process.pid),'-o','time='],text=True).strip();parts=text.split(':');return float(parts[-1])+int(parts[-2])*60+(int(parts[-3])*3600 if len(parts)>2 else 0)
def screenshot(name):
 g.qmp('screendump',{'filename':str(out/(name+'.ppm'))})
 from PIL import Image
 im=Image.open(out/(name+'.ppm')).convert('RGB');assert im.size==(800,600);im.save(out/(name+'.png'));return im
try:
 with tempfile.TemporaryDirectory(prefix='xos_virtio_pixels_') as tmp:
  tmp=Path(tmp);screens={}
  for backend in ('vbe','virtio'):
   disk=tmp/(backend+'.img');create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/gui.elf',a.qt_payload)
   if a.access_payload:transfer(disk,'import','/bin/access.elf',a.access_payload)
   boot(disk,backend,backend);base=resources(g)
   if backend=='virtio':report['pci']=g.qmp('query-pci')
   result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',result)[1]);g.expect(b'[display-service] ready');with_service=resources(g)
   command(g,'exec gfxdemo check',b'checks=pass');assert resources(g)==with_service
   start=len(g.output);send_bytes(g,b'exec-file /bin/gui.elf pixels\r');g.expect(b'QT_GUI_PIXEL_REFERENCE_READY',start=start,timeout=90);screens[backend]=screenshot(backend+'-pixels')
   stroke('esc');g.expect(b'kind=exited code=0',start=start,timeout=30);g.expect_supervisor(start=start);assert resources(g)==with_service
   data=bytes(g.output)[start:];assert b'input-thread-joined' in data
   if backend=='virtio':
    frames=[tuple(map(int,m)) for m in re.findall(rb'\[virtio-gpu-frame\] x=(\d+) y=(\d+) w=(\d+) h=(\d+) requests=(\d+) completed=(\d+)',data)]
    assert any(w*h<800*600 for x,y,w,h,_,_ in frames) and all(req==done for *_,req,done in frames),frames
   # Same workload/ELF; process CPU time is an observation, not a speed claim.
   samples=[]
   for i in range(3):
    cpu=cpu_seconds();wall=time.monotonic();r=command(g,'exec-file /bin/gui.elf auto',b'kind=exited code=0',timeout=90);elapsed=time.monotonic()-wall;used=cpu_seconds()-cpu;assert b'QT_GUI_OK' in r;assert resources(g)==with_service
    samples.append({'wall_seconds':elapsed,'qemu_process_cpu_seconds':used,'qemu_process_cpu_percent':used/elapsed*100,'present_ns':[int(x) for x in re.findall(rb'\[qpa-frame\][^\n]* ns=(\d+)',r)]})
   # Existing real Qt input/lifecycle and service restart against this backend.
   for mode in ('repeat','focus','fault','second'):
    r=command(g,'exec-file /bin/gui.elf '+mode,b'kind=faulted' if mode=='fault' else b'kind=exited',timeout=90)
    if mode not in ('fault','second'):assert b'QT_GUI_OK' in r
    assert resources(g)==with_service
   start=len(g.output);send_bytes(g,b'spawn-file /bin/gui.elf hold\r');g.expect(b'QT_GUI_READY',start=start,timeout=90);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[start:])[1]);stroke('a');g.expect(b'text=a',start=start)
   g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':31}},{'type':'rel','data':{'axis':'y','value':17}},{'type':'btn','data':{'button':'left','down':True}}]});g.expect(b'[qt-mouse] press',start=start)
   g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':False}}]})
   command(g,f'kill {service}',b'kill: accepted');command(g,f'wait {pid}',b'kind=exited code=72');command(g,f'wait {service}',b'kind=killed');assert resources(g)==base
   r=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',r)[1]);g.expect(b'[display-service] ready');with_service=resources(g)
   command(g,'exec-file /bin/gui.elf auto',b'kind=exited code=0',timeout=90);assert resources(g)==with_service
   if a.access_payload:
    for argument,vector in [('',14),(' ports',13)]:
     r=command(g,'exec-file /bin/access.elf'+argument,b'kind=faulted',timeout=30);assert f'vector={vector}'.encode() in r;assert resources(g)==with_service
   command(g,'sync',b'[files] sync=ok');command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base
   cmd=g.command;close(backend)
   reference=out/(backend+'-qimage.bin');transfer(disk,'export','/qtframe.bin',reference)
   from PIL import Image
   expected=Image.frombytes('RGB',(800,600),reference.read_bytes(),'raw','BGRX');assert expected.tobytes()==screens[backend].tobytes(),backend
   report['runs'].append({'backend':backend,'baseline':base,'with_service':with_service,'qemu_command':cmd,'pixel_sha256':hashlib.sha256(screens[backend].tobytes()).hexdigest(),'qt_reference_sha256':sha(reference),'cpu_observations':samples,'pixel_comparison':'1,440,000 RGB bytes exact; X is unused by B8G8R8X8/XRGB8888'})
   print(backend,'PASSED',flush=True)
  assert screens['vbe'].tobytes()==screens['virtio'].tobytes();report['checks']=['actual_virtio_PCI_VERSION1_queue_and_fenced_completions','scatter_DMA_create_attach_scanout_transfer_flush','dirty_rect_offsets_exact_Qt_reference_pixels','same_frame_VBE_and_VirtIO_exact_RGB','device_invalid_resource_bounds_cycles_reset_free_pages','PS2_keys_mouse_actual_Qt_events','client_fault_second_window_and_repeated_window_lifetime','service_death_and_restart_exact_resource_baselines','user_MMIO_and_PCI_IO_fault_isolation','same_workload_present_and_host_process_CPU_observations'];report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:close('failed')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
