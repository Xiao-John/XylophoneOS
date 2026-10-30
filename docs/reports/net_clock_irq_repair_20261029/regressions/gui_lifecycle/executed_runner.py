#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""G04 real XOS guest: raster bytes, text, PS/2, blocking and lifecycle failures."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
from unittest.mock import patch
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/gui_lifecycle')
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import boot_smoke
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--case',choices=['interactive','pixels','lifecycle','no-vga'],required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 report={'status':'FAILED','case':a.case,'image_sha256':sha(a.image),'elf_sha256':sha(a.payload),'checks':[]}
 receipt=json.loads(a.payload.with_suffix('.receipt.json').read_text())
 assert sha(a.payload)==receipt['elf_sha256']
 for path,digest in receipt['inputs'].items():assert sha(Path(path))==digest,path
 report['build_receipt_sha256']=sha(a.payload.with_suffix('.receipt.json'))
 g=None
 def mark(name,**fields):
  report['checks'].append({'name':name,'status':'PASSED',**fields})
  print(name,'PASSED',flush=True)
 def key(k,down):
  g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':k}}}]})
 def stroke(k):key(k,True);key(k,False)
 def start(mode,background=False):
  begin=len(g.output);send_bytes(g,('spawn-file' if background else 'exec-file').encode()+b' /bin/qtgui.elf '+mode.encode()+b'\r')
  g.expect(b'QT_GUI_READY',start=begin,timeout=90)
  g.expect(b'[qpa-frame]',start=begin,timeout=30)
  return begin
 def finish(begin,code=0):
  g.expect(f'kind=exited code={code}'.encode(),start=begin,timeout=30);g.expect_supervisor(start=begin)
  if code==0: assert b'input-thread-joined' in bytes(g.output)[begin:]
 def service_start():
  b=len(g.output);r=command(g,'display-start',b'result=0');g.expect(b'[display-service] ready',start=b)
  return int(re.search(rb'\[display-start\] pid=(\d+)',r)[1])
 def service_stop(pid):
  command(g,'exec gfxdemo stop',b'kind=exited code=0')
  command(g,f'wait {pid}',b'kind=exited code=0')
 try:
  with tempfile.TemporaryDirectory(prefix='xos_qt_g04_') as d:
   disk=Path(d)/'test.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/qtgui.elf',a.payload)
   original=boot_smoke.qemu_command
   def qemu(*args,**kw):
    cmd=original(*args,**kw)
    if a.case=='no-vga':cmd[cmd.index('-vga')+1]='none'
    return cmd
   name=str(out.relative_to(ROOT/'build'))+'/guest'
   with patch.object(boot_smoke,'qemu_command',qemu):g=Guest(a.image.resolve(),name,work_disk=disk)
   report['qemu_command']=g.command
   g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.5)
   baseline=resources(g);report['baseline']=baseline
   if a.case=='no-vga':
    result=command(g,'exec-file /bin/qtgui.elf auto',b'kind=exited',timeout=90)
    assert b'unavailable or invalid Display Service mode (-19)' in result,result[-1500:]
    assert b'QT_GUI_READY' not in result
    assert resources(g)==baseline
    mark('missing_graphics_device_fails_explicitly_and_serial_recovers')
   else:
    service=service_start();with_service=resources(g);report['with_service']=with_service
    if a.case=='pixels':
     begin=start('pixels');g.expect(b'QT_GUI_PIXEL_REFERENCE_READY',start=begin,timeout=30)
     physical=int(re.search(rb'\[display\][^\n]*physical=(0x[0-9a-f]+)',g.output)[1],16)
     mode=re.search(rb'width=(\d+) height=(\d+) stride=(\d+) format=(\d+)',bytes(g.output)[begin:])
     width,height,stride,fmt=map(int,mode.groups());assert fmt==1
     g.qmp('pmemsave',{'val':physical,'size':height*stride,'filename':str(out/'scanout.bin')})
     g.qmp('screendump',{'filename':str(out/'scanout.ppm')})
     from PIL import Image
     image=Image.open(out/'scanout.ppm');assert image.size==(width,height)
     assert image.getpixel((0,0))==(0x12,0x34,0x56)
     assert image.getpixel((width-1,height-1))==(0xab,0xcd,0xef)
     assert image.getpixel((50,150))==(239,68,68)
     assert image.getpixel((220,150))==(245,158,11)
     # Title uses a real font; require antialiased light ink across its region.
     ink=sum(1 for r,gc,b in image.crop((40,35,600,70)).get_flattened_data() if r>150 and gc>150 and b>150)
     assert ink>1000,ink
     image.save(out/'scanout.png')
     stroke('esc');finish(begin)
     assert resources(g)==with_service
     command(g,'sync',b'[files] sync=ok');service_stop(service);assert resources(g)==baseline
     g.close();g=None
     transfer(disk,'export','/qtframe.bin',out/'qtimage.bin')
     reference=(out/'qtimage.bin').read_bytes();device=(out/'scanout.bin').read_bytes()
     assert len(reference)==width*height*4
     for y in range(height):assert reference[y*width*4:(y+1)*width*4]==device[y*stride:y*stride+width*4],y
     mark('qimage_exact_bytes_equal_scanout_full_dirty_clip_font_and_xrgb',width=width,height=height,stride=stride,text_ink_pixels=ink,
          image_sha256=sha(out/'qtimage.bin'),framebuffer_sha256=sha(out/'scanout.bin'),screenshot_sha256=sha(out/'scanout.png'))
    elif a.case=='interactive':
     begin=start('overflow');pump(g,.3)
     stroke('a');key('shift',True);stroke('b');key('shift',False)
     key('ctrl',True);stroke('c');key('ctrl',False);key('alt',True);stroke('d');key('alt',False)
     g.expect(b'[qt-key] press key=66 mods=33554432 text=B',start=begin)
     g.expect(b'[qt-key] release key=66',start=begin)
     g.expect(b'[qt-key] press key=67 mods=67108864',start=begin)
     g.expect(b'[qt-key] press key=68 mods=134217728',start=begin)
     g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':31}}, {'type':'rel','data':{'axis':'y','value':17}}, {'type':'btn','data':{'button':'left','down':True}}]})
     g.expect(b'[qt-mouse] press button=1',start=begin)
     g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':False}}]})
     g.expect(b'[qt-mouse] release button=1',start=begin)
     g.expect(b'[qt-mouse] move x=431 y=317',start=begin)
     mark('qmp_ps2_english_shift_ctrl_alt_release_mouse_position_and_click')
     # First press pauses the real input worker; hardware FIFO still receives IRQs.
     key('p',True);g.expect(b'QT_INPUT_PAUSE_ARMED',start=begin)
     key('p',False)
     for i in range(80):stroke('b');time.sleep(.002)
     g.expect(b'kind=4',start=begin,timeout=15);pump(g,.4)
     data=bytes(g.output)[begin:]
     events=[tuple(map(int,m)) for m in re.findall(rb'\[qpa-input\] seq=(\d+) ns=(\d+) kind=(\d+) code=(\d+) mods=(\d+) buttons=(\d+) lost=(\d+) gui_ns=(\d+)',data)]
     assert any(e[2]==4 and e[6]>=65 for e in events)
     assert b'[qt-key] release key=80' in data
     assert all(x[0]<y[0] for x,y in zip(events,events[1:]))
     mark('real_64_entry_queue_overflow_resync_releases_held_keys_order_preserved',events=events)
     stroke('a');g.expect(b'text=a',start=begin)
     g.qmp('screendump',{'filename':str(out/'interactive.ppm')})
     from PIL import Image
     Image.open(out/'interactive.ppm').save(out/'interactive.png')
     stroke('esc');finish(begin);assert resources(g)==with_service
     mark('gui_exit_cancels_hardware_wait_and_joins_thread_resources_restored')
     service_stop(service);assert resources(g)==baseline
    else:
     for mode in ('auto','repeat','focus','idle','oom','quota','fault','second'):
      begin=len(g.output)
      result=command(g,'exec-file /bin/qtgui.elf '+mode,b'kind=faulted' if mode=='fault' else b'kind=exited',timeout=90)
      if mode=='fault':assert b'QT_GUI_FAULT_TRIGGER' in result and b'vector=6' in result
      elif mode=='quota':assert b'input thread resource allocation failed' in result
      elif mode=='second':assert b'exclusive Surface connect failed (-16)' in result
      else:
       assert b'QT_GUI_OK' in result and b'kind=exited code=0' in result
       assert result.count(b'input-thread-joined')==(3 if mode=='repeat' else 1)
       if mode=='focus':assert b'QT_GUI_FOCUS_OUT_OK' in result and b'QT_GUI_FOCUS_IN_OK' in result
       if mode=='idle':assert int(re.search(rb'QT_GUI_IDLE waiting=(\d+)',result)[1])>=2
       if mode=='oom':assert b'QT_GUI_IMAGE_OOM_NULL_OK' in result
      assert resources(g)==with_service
      mark('client_'+mode+'_resource_recovery')
     begin=start('hold',True)
     pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[begin:])[1])
     command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed')
     assert resources(g)==with_service
     mark('client_kill_with_input_wait_and_timer_reclaims_surface_and_thread')
     begin=start('hold',True)
     pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[begin:])[1])
     command(g,f'kill {service}',b'kill: accepted');pump(g,.2)
     command(g,f'wait {pid}',b'kind=exited code=72');command(g,f'wait {service}',b'kind=killed')
     assert resources(g)==baseline
     mark('service_death_wakes_input_and_client_exits_all_resources_return')
     service=service_start();with_service=resources(g)
     result=command(g,'exec-file /bin/qtgui.elf auto',b'kind=exited code=0',timeout=90)
     assert b'QT_GUI_OK' in result;assert resources(g)==with_service
     service_stop(service);assert resources(g)==baseline
     mark('service_restart_new_qt_client_recovers_and_serial_rescue_works')
     result=command(g,'display-start fault',b'result=0')
     fault_service=int(re.search(rb'\[display-start\] pid=(\d+)',result)[1])
     result=command(g,'exec-file /bin/qtgui.elf auto',b'kind=exited code=72',timeout=90)
     assert b'present failed (-19)' in result or b'Display Service disconnected' in result
     command(g,f'wait {fault_service}',b'kind=faulted');assert resources(g)==baseline
     mark('service_fault_during_real_qt_present_releases_inflight_ipc')
   report['status']='PASSED'
 except Exception as e:
  report['error']=str(e);raise
 finally:
  if g:
   (out/'serial.log').write_bytes(g.output);g.close()
  elif (out/'guest_serial.log').exists():(out/'serial.log').write_bytes((out/'guest_serial.log').read_bytes())
  if (out/'serial.log').exists():
   data=(out/'serial.log').read_bytes()
   report['measurements']={
    'sampled_peak_user_pages':max([int(x) for x in re.findall(rb'sampled_pages=(\d+)',data)] or [0]),
    'present_duration_ns':[int(x) for x in re.findall(rb'\[qpa-frame\][^\n]* ns=(\d+)',data)],
    'paint_duration_ns':[int(x) for x in re.findall(rb'\[qt-demo\] paint[^\n]* ns=(\d+)',data)],
    'normal_key_latency_ns':[int(x) for x in re.findall(rb'\[qt-key\] press[^\n]* latency_ns=(\d+)',data.split(b'QT_INPUT_PAUSE_ARMED')[0])],
    'clock_resolution_ns':10000000,'absolute_peak':'NOT_RUN','cpu_percentage':'NOT_RUN'}
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status'])
if __name__=='__main__':main()
