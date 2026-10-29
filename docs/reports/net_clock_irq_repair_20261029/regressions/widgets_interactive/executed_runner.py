#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""G05: real Aurora Widgets, PS/2 editing, files, scanout and process lifetime."""
import argparse,hashlib,json,re,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/widgets_interactive')
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import boot_smoke
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--case',choices=['interactive','lifecycle','no-vga'],required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
receipt=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==receipt['elf_sha256']
for name,h in receipt['inputs'].items():assert sha(name)==h,name
report={'status':'FAILED','case':a.case,'image_sha256':sha(a.image),'elf_sha256':sha(a.payload),'receipt_sha256':sha(a.payload.with_suffix('.receipt.json')),'checks':[]};g=None
original=('A little more imagination.\n\nA quiet place for a bright idea.\n\n# Welcome to XylophoneOS\n\nSimple tools, carefully made.\nYour words stay local.\n\nUTF-8: café — Ελληνικά\n').encode()
longtext=('Long notes\n'+''.join(f'Line {i:03d}: A thought worth keeping.\n' for i in range(300))).encode()
def mark(name,**kw):report['checks'].append({'name':name,'status':'PASSED',**kw});print(name,'PASSED',flush=True)
def key(k,d):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':d,'key':{'type':'qcode','data':k}}}]})
def stroke(k):key(k,True);key(k,False);pump(g,.035)
def chord(mod,k):key(mod,True);stroke(k);key(mod,False);pump(g,.06)
def type_text(s):
 codes={'/':'slash','.':'dot','-':'minus',' ':'spc','\n':'ret'}
 for c in s:
  if c.isupper():key('shift',True)
  stroke(codes.get(c,c.lower()))
  if c.isupper():key('shift',False)
def point(name):
 data=bytes(g.output);m=list(re.finditer(('EDITOR_POINT '+name+r'=(\d+),(\d+)').encode(),data));assert m,name
 return tuple(map(int,m[-1].groups()))
def click(name):
 x,y=point(name)
 # Drive the actual PS/2 pointer to a known corner, then to the control.
 for i in range(5):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-200}},{'type':'rel','data':{'axis':'y','value':-200}}]})
 for dx,dy in [(min(200,x-i),min(200,y-i)) for i in range(0,max(x,y),200)]:
  g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':max(0,dx)}},{'type':'rel','data':{'axis':'y','value':max(0,dy)}}]})
 pump(g,.1)
 for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':down}}]});pump(g,.1)
def screenshot(name):
 g.qmp('screendump',{'filename':str(out/(name+'.ppm'))})
 from PIL import Image
 im=Image.open(out/(name+'.ppm'));assert im.size==(800,600);im.save(out/(name+'.png'))
 report.setdefault('screenshots',{})[name]=sha(out/(name+'.png'))
def start(path='/note.txt',background=False):
 b=len(g.output);send_bytes(g,('spawn-file' if background else 'exec-file').encode()+b' /bin/notes.elf '+path.encode()+b'\r')
 g.expect(b'QT_EDITOR_READY',start=b,timeout=90);pump(g,.3);return b
def finish(b,code=0,background=False):
 if background:
  pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'wait {pid}',f'kind=exited code={code}'.encode())
 else:g.expect(f'kind=exited code={code}'.encode(),start=b,timeout=30);g.expect_supervisor(start=b)
 if code==0:assert b'input-thread-joined' in bytes(g.output)[b:]
def service_start():
 b=len(g.output);r=command(g,'display-start',b'result=0');g.expect(b'[display-service] ready',start=b);return int(re.search(rb'\[display-start\] pid=(\d+)',r)[1])
def service_stop(pid):command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {pid}',b'kind=exited code=0')
def boot(disk,name,no_vga=False):
 global g
 orig=boot_smoke.qemu_command
 def qemu(*args,**kw):
  cmd=orig(*args,**kw)
  if no_vga:cmd[cmd.index('-vga')+1]='none'
  return cmd
 with patch.object(boot_smoke,'qemu_command',qemu):g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/'+name,work_disk=disk)
 report.setdefault('qemu_commands',[]).append(g.command);g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3)
def shutdown(name):
 global g
 (out/(name+'.serial.log')).write_bytes(g.output);g.close();g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_g05_') as temp:
  d=Path(temp);disk=d/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/notes.elf',a.payload)
  for name,data in [('note.txt',original),('long.txt',longtext),('crlf.txt',b'\xef\xbb\xbfFirst\r\nSecond\r\n'),('empty.txt',b''),('noeol.txt',b'No newline')]:
   f=d/name;f.write_bytes(data);transfer(disk,'import','/'+name,f)
  boot(disk,'guest',a.case=='no-vga');base=resources(g);report['baseline']=base
  if a.case=='no-vga':
   r=command(g,'exec-file /bin/notes.elf /note.txt',b'kind=exited',timeout=90);assert b'unavailable or invalid Display Service mode (-19)' in r;assert resources(g)==base;mark('no_graphics_explicit_failure_and_serial_rescue')
  else:
   service=service_start();with_service=resources(g);report['with_service']=with_service
   if a.case=='interactive':
    b=start();screenshot('aurora-open');chord('ctrl','end');type_text('hello\nworld');stroke('home');key('shift',True)
    for _ in range(5):stroke('right')
    key('shift',False);g.expect(b'EDITOR_SELECTION',start=b);screenshot('selection');type_text('WORLD');stroke('backspace');key('shift',True);stroke('d');key('shift',False)
    sb=len(g.output);chord('ctrl','s');g.expect(b'EDITOR_SAVE_OK',start=sb,timeout=30)
    expected=original+b'hello\nWORLD';assert b'EDITOR_CHANGE characters=' in bytes(g.output)[b:]
    mark('real_ps2_multiline_shift_selection_delete_insert_arrows_ctrl_s')
    chord('ctrl','home');click('document');pump(g,1.1);assert int(re.findall(rb'EDITOR_SAMPLE[^\n]* cursor=(\d+)',bytes(g.output)[b:])[-1])>0;mark('ps2_mouse_positions_real_text_cursor')
    chord('ctrl','o');type_text('/long.txt');stroke('ret');g.expect(b'EDITOR_OPEN_OK bytes='+str(len(longtext)).encode(),start=b);chord('ctrl','end');pump(g,1.1)
    assert max(map(int,re.findall(rb'EDITOR_SAMPLE[^\n]* scroll=(\d+)',bytes(g.output)[b:])))>0;screenshot('long-scroll');mark('long_document_scroll_and_viewport_clipping')
    sb=len(g.output);chord('ctrl','s');g.expect(b'EDITOR_SAVE_OK',start=sb,timeout=30)
    type_text('a');stroke('esc');g.expect(b'EDITOR_UNSAVED_GUARD',start=b);pump(g,.15);screenshot('unsaved');click('cancel');type_text('b');stroke('esc');pump(g,.2);click('discard');finish(b)
    assert resources(g)==with_service;mark('inline_unsaved_cancel_discard_and_full_resource_recovery')
    for path in ('/crlf.txt','/empty.txt','/noeol.txt'):
     b=start(path);sb=len(g.output);chord('ctrl','s');g.expect(b'EDITOR_SAVE_OK',start=sb);stroke('esc');finish(b);assert resources(g)==with_service
    mark('bom_crlf_empty_and_no_trailing_newline_roundtrip')
    b=start('/new.txt');type_text('new\nfile');sb=len(g.output);chord('ctrl','s');g.expect(b'EDITOR_SAVE_OK',start=sb);stroke('esc');finish(b);assert resources(g)==with_service;mark('new_file_creation')
    command(g,'sync',b'[files] sync=ok');service_stop(service);assert resources(g)==base;shutdown('first')
    comparisons={}
    for name,wanted in [('note.txt',expected),('long.txt',longtext),('crlf.txt',b'\xef\xbb\xbfFirst\r\nSecond\r\n'),('empty.txt',b''),('noeol.txt',b'No newline'),('new.txt',b'new\nfile')]:
     target=d/('export-'+name);transfer(disk,'export','/'+name,target);assert target.read_bytes()==wanted,name;comparisons[name]={'bytes':len(wanted),'sha256':sha(target)}
    boot(disk,'reboot');service=service_start();b=start();assert b'EDITOR_OPEN_OK bytes='+str(len(expected)).encode() in bytes(g.output)[b:];stroke('esc');finish(b);command(g,'sync',b'[files] sync=ok');service_stop(service);mark('sync_reboot_byte_exact_readback',comparisons=comparisons)
   else:
    for i in range(3):
     b=start();stroke('esc');finish(b);assert resources(g)==with_service
    mark('three_widget_create_exit_cycles_resources_exact')
    b=start(background=True);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed');assert resources(g)==with_service;mark('killed_editor_reclaims_input_surface_and_heap')
    b=start(background=True);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'kill {service}',b'kill: accepted');command(g,f'wait {pid}',b'kind=exited code=72');command(g,f'wait {service}',b'kind=killed');assert resources(g)==base;mark('display_death_exits_widgets_client_and_serial_survives')
    service=service_start();with_service=resources(g);b=start();stroke('esc');finish(b);assert resources(g)==with_service;service_stop(service);assert resources(g)==base;mark('display_restart_new_editor_recovers')
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:shutdown('final')
 data=b''.join(p.read_bytes() for p in out.glob('*.serial.log'))
 report['measurements']={'sampled_peak_pages':max([int(x) for x in re.findall(rb'EDITOR_SAMPLE pages=(\d+)',data)] or [0]),'input_latency_ns':[int(x) for x in re.findall(rb'EDITOR_KEY[^\n]* latency_ns=(\d+)',data)],'present_ns':[int(x) for x in re.findall(rb'\[qpa-frame\][^\n]* ns=(\d+)',data)],'visual_cache':[(int(x),int(y)) for x,y in re.findall(rb'AURORA_CACHE bytes=(\d+) ns=(\d+)',data)],'absolute_peak':'NOT_RUN','clock_resolution_ns':10000000}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
