#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real QEMU VirtIO-Net Ethernet frames over an isolated loopback socket backend."""
import argparse, hashlib, json, socket, struct, sys, threading, time
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/n1_jumbo_qt')
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes
p=argparse.ArgumentParser();p.add_argument('--system',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['echo','timeout','absent','quota','overflow','jumbo'],default='echo');p.add_argument('--gpu',action='store_true');p.add_argument('--access-payload',type=Path);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
manifest=json.loads((a.system/'manifest.json').read_text());image=a.system.resolve()/'xos-install.iso'
sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(image.read_bytes())==manifest['artifacts']['xos-install.iso']['sha256']
report={'status':'FAILED','mode':a.mode,'build_id':manifest['build_id'],'image_sha256':sha(image.read_bytes()),'host_frames':[],'runs':[]};g=None;server=None;thread=None;errors=[];frames=[];stop=threading.Event()
def exact(conn,n):
 data=b''
 while len(data)<n:
  chunk=conn.recv(n-len(data))
  if not chunk:raise EOFError()
  data+=chunk
 return data
def host():
 try:
  conn,_=server.accept();conn.settimeout(120)
  with conn:
   while not stop.is_set():
    n=struct.unpack('!I',exact(conn,4))[0];assert 14<=n<=1514
    data=exact(conn,n);index=len(frames);(out/f'host_rx_{index:03}.bin').write_bytes(data)
    seq=data[14];length=1514 if seq==15 else 60+seq*23
    assert len(data)==length and data[:6]==b'\xff'*6 and data[6:14]==bytes.fromhex('52540012345688b5')
    assert data[15:]==bytes((i+seq)&255 for i in range(15,length))
    frames.append({'index':index,'sequence':seq,'length':length,'sha256':sha(data)})
    if a.mode in ('echo','overflow'):
     # Invalid Ethernet lengths must be observed/rejected by the guest, not just host.
     if seq==0:
      for bad in (b'\xff'*6+b'X'*4,b'\xff'*6+b'Y'*1509):conn.sendall(struct.pack('!I',len(bad))+bad)
     conn.sendall(struct.pack('!I',len(data))+data)
     if a.mode=='overflow' and seq==15:
      for _ in range(8):conn.sendall(struct.pack('!I',len(data))+data)
    if a.mode=='jumbo' and seq==0:
     data=b'\xff'*6+b'Z'*4994;conn.sendall(struct.pack('!I',len(data))+data)
 except (EOFError,ConnectionResetError,BrokenPipeError):pass
 except Exception as e:
  if not stop.is_set():errors.append(repr(e))
try:
 if a.mode!='absent':
  server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1);server.settimeout(20)
  thread=threading.Thread(target=host,daemon=True);thread.start()
 disk=None
 if a.access_payload:
  from make_work_disk import create_fat32
  from work_disk import transfer
  disk=out/'probe_disk.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/access.elf',a.access_payload);transfer(disk,'import','/bin/gui.elf',Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e17/build/qt_e17/final_gui/qt_demo.elf'))
  report['access_elf_sha256']=sha(a.access_payload.read_bytes())
 original=boot_smoke.qemu_command
 def command(*args,**kwargs):
  cmd=original(*args,**kwargs)
  if a.mode!='absent':cmd+=['-netdev',f'socket,id=net,connect=127.0.0.1:{server.getsockname()[1]}','-device','virtio-net-pci,netdev=net,disable-legacy=on,mac=52:54:00:12:34:56']
  if a.gpu:cmd[cmd.index('-vga')+1]='none';cmd+=['-device','virtio-gpu-pci,disable-legacy=on']
  return cmd
 with patch.object(boot_smoke,'qemu_command',command):g=Guest(image,str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk)
 g.expect(b'xos64> ',timeout=60);report['qemu_command']=g.command;report['pci']=g.qmp('query-pci')
 for run in range(2 if a.mode=='echo' else 1):
  start=len(g.output);operation='net-'+a.mode if a.mode in ('timeout','overflow','jumbo') else 'net-test';send_bytes(g,(operation+'\r').encode())
  marker=b'net-test unavailable_or_failed' if a.mode in ('absent','quota') else (operation+' pass').encode()
  g.expect(marker,start=start,timeout=30);g.expect(b'xos64> ',start=start)
  segment=bytes(g.output[start:]);report['runs'].append(segment.decode(errors='replace'))
  if a.mode in ('echo','overflow'):assert b'rx=16 tx_completed=16' in segment and b'rejected=2 ' in segment and b'reclaimed=34 ' in segment
  if a.mode=='overflow':assert b'dropped=8 ' in segment
  if a.mode=='jumbo':assert b'failed=1 ' in segment and b'reclaimed=34 ' in segment
  if a.mode=='quota':assert b'features_queue_or_DMA_failure' in segment
  if a.mode=='absent':assert b'absent modern_id=1af4:1041' in segment
 send_bytes(g,b'run\r');g.expect_supervisor(trace=bool(a.access_payload),timeout=30);report['old_system_boot']='PASSED'
 if a.access_payload:
  import re
  from process_smoke import command,resources
  command(g,'demo quiet',b'demo tasks')
  pre=resources(g)
  started=command(g,'display-start',b'result=0')
  service=int(re.search(rb'pid=(\d+)',started)[1])
  g.expect(b'[display-service] ready')
  with_service=resources(g)
  start=len(g.output);send_bytes(g,b'exec-file /bin/gui.elf pixels\r')
  g.expect(b'QT_GUI_PIXEL_REFERENCE_READY',start=start,timeout=90)
  g.qmp('screendump',{'filename':str(out/'after-network-fault.ppm')})
  from PIL import Image
  Image.open(out/'after-network-fault.ppm').save(out/'after-network-fault.png')
  for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':'esc'}}}]})
  g.expect(b'kind=exited code=0',start=start,timeout=30);g.expect(b'xsh> ',start=start)
  assert resources(g)==with_service
  command(g,'exec gfxdemo stop',b'kind=exited code=0')
  command(g,f'wait {service}',b'kind=exited code=0')
  assert resources(g)==pre
  report['same_boot_Qt_after_network_failure']='PASSED'
  report['Qt_pre_resources']=pre
  report['Qt_with_display_service_resources']=with_service
  report['Qt_ELF_sha256']=sha(Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e17/build/qt_e17/final_gui/qt_demo.elf').read_bytes())
 if a.access_payload:
  from process_smoke import command,resources
  command(g,'demo quiet',b'demo tasks')
  baseline=resources(g)
  for argument,vector in [('',14),(' ports',13)]:
   result=command(g,'exec-file /bin/access.elf'+argument,b'kind=faulted',timeout=30)
   assert f'vector={vector}'.encode() in result,result
   assert resources(g)==baseline
  report['ordinary_user_MMIO_PCI_IO_denied']='PASSED'
  report['fault_resource_baseline']=baseline
  command(g,'sync',b'[files] sync=ok')
 assert not errors,errors
 if a.mode=='echo':assert len(frames)==32 and [x['sequence'] for x in frames]==list(range(16))*2
 if a.mode=='timeout':assert len(frames)==16
 report['host_frames']=frames;report['status']='PASSED'
finally:
 stop.set()
 if g:(out/'guest.serial.log').write_bytes(g.output);g.close()
 if server:server.close()
 if thread:thread.join(timeout=1)
 report['host_errors']=errors;report['host_frames']=frames
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
