#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real PS/2 guest evidence for Aurora G0/G1; no simulated compositor."""
import argparse,hashlib,json,re,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
p=argparse.ArgumentParser()
for name in ('image','target','output'):p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--case',choices=['interactive','session','lifecycle','studio'],default='interactive')
p.add_argument('--notes',type=Path);p.add_argument('--browser',type=Path);p.add_argument('--legacy',type=Path)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
payloads={'desktop':a.target/'desktop/desktop.elf','studio':a.target/'studio/studio.elf','session':a.target/'session.elf','gap':a.target/'compositor_gap.elf'}
for name in ('notes','browser','legacy'):
 if getattr(a,name):payloads[name]=getattr(a,name)
for payload in payloads.values():
 receipt=payload.with_suffix('.receipt.json')
 if receipt.exists():
  r=json.loads(receipt.read_text());assert sha(payload)==r['elf_sha256']
  for f,digest in r['inputs'].items():assert sha(f)==digest,f
report={'status':'FAILED','case':a.case,'image_sha256':sha(a.image),'elf_sha256':{k:sha(v) for k,v in payloads.items()},'checks':[],'screenshots':{},'latency_host_ms':[]};g=None
def mark(name,**kw):report['checks'].append({'name':name,'status':'PASSED',**kw});print(name,'PASSED',flush=True)
def key(k,down):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':k}}}]})
def stroke(k):key(k,True);key(k,False);pump(g,.05)
def chord(mod,k):key(mod,True);stroke(k);key(mod,False);pump(g,.15)
def shot(name):
 pump(g,1.0)
 g.qmp('screendump',{'filename':str(out/(name+'.ppm'))});from PIL import Image
 im=Image.open(out/(name+'.ppm'));im.save(out/(name+'.png'));report['screenshots'][name]=sha(out/(name+'.png'));return im
def click_xy(x,y):
 for _ in range(10):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-100}},{'type':'rel','data':{'axis':'y','value':-100}}]});pump(g,.02)
 for offset in range(0,max(x,y),80):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':min(80,max(0,x-offset))}},{'type':'rel','data':{'axis':'y','value':min(80,max(0,y-offset))}}]});pump(g,.02)
 pump(g,.08)
 for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':down}}]});pump(g,.08)
def click(name,expected=None):
 match=list(re.finditer(rb'DESKTOP_POINT name='+re.escape(name.encode())+rb' xy=(\d+),(\d+)',bytes(g.output)))[-1]
 start=len(g.output);t=time.monotonic();click_xy(*map(int,match.groups()))
 if expected:g.expect(expected,start=start,timeout=40)
 report['latency_host_ms'].append(round((time.monotonic()-t)*1000,2));pump(g,1.0);return start
try:
 with tempfile.TemporaryDirectory(prefix='xos_desktop_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'mkdir','/web')
  for name,f in payloads.items():transfer(disk,'import','/bin/'+name+'.elf',f)
  if a.browser:
   for f in (ROOT/'src/ports/aurora_browser/pages').iterdir():transfer(disk,'import','/web/'+f.name,f)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3)
  base=resources(g);service_result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',service_result)[1]);g.expect(b'[display-service] ready');with_service=resources(g)
  report['baseline']=base;report['with_service']=with_service
  def start(background=False,app='desktop',args=''):
   b=len(g.output);send_bytes(g,('spawn-file' if background else 'exec-file').encode()+f' /bin/{app}.elf{args}\r'.encode());g.expect(b'STUDIO_READY' if app=='studio' else b'DESKTOP_READY',start=b,timeout=90);pump(g,.4);return b
  def finish(b,app='desktop'):
   if app=='desktop':chord('ctrl','q')
   else:stroke('esc')
   g.expect(b'kind=exited code=0',start=b,timeout=30);g.expect_supervisor(start=b);assert resources(g)==with_service
  if a.case=='session':
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf\r');g.expect(b'DESKTOP_READY',start=b,timeout=90);pump(g,.4)
   for name,id,ready in [('Notes',1,b'QT_EDITOR_READY'),('Browser',2,b'BROWSER_READY'),('SDK Studio',3,b'STUDIO_READY')]:
    if id==3:click('Apps',b'DESKTOP_PAGE index=1')
    sb=click(name,b'SESSION_APP_STARTED app='+str(id).encode())
    g.expect(ready,start=sb,timeout=90);pump(g,.4);shot('launched-'+str(id));stroke('esc')
    if id==1:
     pump(g,.3)
     if b'EDITOR_UNSAVED_GUARD' in bytes(g.output)[sb:]:
      g.expect(b'EDITOR_POINT discard=',start=sb)
      match=list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)',bytes(g.output)[sb:]))[-1]
      click_xy(*map(int,match.groups()))
    g.expect(b'SESSION_APP_ENDED app='+str(id).encode(),start=sb,timeout=30);g.expect(b'DESKTOP_READY',start=sb,timeout=90);pump(g,.5)
    mark('independent_application_handoff_'+str(id))
   finish(b);mark('session_exit_exact_resources')
  elif a.case=='studio':
   b=start(app='studio');shot('independent-studio-dark');click_xy(*map(int,re.findall(rb'STUDIO_POINT name=theme xy=(\d+),(\d+)',bytes(g.output))[-1]));g.expect(b'STUDIO_THEME',start=b);shot('independent-studio-light')
   click_xy(*map(int,re.findall(rb'STUDIO_POINT name=menu xy=(\d+),(\d+)',bytes(g.output))[-1]));g.expect(b'STUDIO_MENU visible=1',start=b);shot('independent-menu')
   click_xy(*map(int,re.findall(rb'STUDIO_POINT name=editor xy=(\d+),(\d+)',bytes(g.output))[-1]));stroke('a');g.expect(b'STUDIO_EDIT',start=b);mark('third_party_standard_controls_theme_menu_edit')
   finish(b,'studio');mark('third_party_exit_exact_resources')
  else:
   b=start(background=a.case=='lifecycle');dark=shot('midnight-home');mark('real_single_surface_desktop')
   if a.case=='interactive':
    click('Settings',b'DESKTOP_PAGE index=3');shot('midnight-settings');sb=click('Daybreak Atelier',b'DESKTOP_THEME_JSON');assert json.loads(re.findall(rb'DESKTOP_THEME_JSON ([^\n]+)',bytes(g.output)[sb:])[-1])['scheme']=='daybreak';light=shot('daybreak-settings')
    assert sum(1 for r,g,b in light.convert('RGB').get_flattened_data() if min(r,g,b)>170)>100000;mark('two_distinct_native_designs')
    for name,field in [('Increase contrast','highContrast'),('Reduce transparency','reduceTransparency'),('Reduce motion','reduceMotion')]:
     sb=click(name,b'DESKTOP_THEME_JSON');data=json.loads(re.findall(rb'DESKTOP_THEME_JSON ([^\n]+)',bytes(g.output)[sb:])[-1]);assert data[field] is True
     shot(field);mark('setting_'+field)
    click('Ribbon wallpaper',b'wallpaper=1');shot('wallpaper-alternative')
    click('Home',b'DESKTOP_PAGE index=0');shot('daybreak-home');click('Hide',b'Panel hidden');shot('panel-hidden');click('Home',b'DESKTOP_PAGE index=0');mark('hide_restore_panel')
    click('Studio',b'DESKTOP_PAGE index=2');shot('component-studio');click('Menu',b'DESKTOP_PAGE index=4');click('Send notification',b'Hello from');shot('notification');click('Back to Studio',b'DESKTOP_PAGE index=2')
    click_xy(250,350);stroke('a');g.expect(b'DESKTOP_EDIT',start=b);stroke('tab');shot('keyboard-focus');mark('real_menu_notification_text_and_keyboard')
    finish(b);mark('desktop_exit_exact_resources')
    command(g,'exec-file /bin/gap.elf',b'kind=exited code=0');mark('display_released_after_desktop')
   else:
    pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1])
    command(g,'exec-file /bin/gap.elf occupied',b'kind=exited code=0');mark('second_process_EBUSY_and_direct_present_denied')
    command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed');assert resources(g)==with_service;mark('desktop_kill_exact_resources')
    b=start(True);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'kill {service}',b'kill: accepted');command(g,f'wait {pid}',b'kind=exited code=72');command(g,f'wait {service}',b'kind=killed');assert resources(g)==base;mark('display_death_fails_closed_serial_survives')
    s=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',s)[1]);g.expect(b'[display-service] ready');with_service=resources(g);b=start();finish(b);mark('desktop_after_service_restart')
  if a.legacy:
   sb=len(g.output);send_bytes(g,b'exec-file /bin/legacy.elf\r');g.expect(b'QT_WIDGETS_READY',start=sb,timeout=90);pump(g,.3);shot('legacy-no-aurora');stroke('esc');g.expect(b'kind=exited code=0',start=sb);g.expect_supervisor(start=sb);assert resources(g)==with_service;mark('non_aurora_app_preserved')
  command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base;command(g,'sync',b'[files] sync=ok');mark('service_stop_and_file_sync');report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:
  report['sampled_pages']=list(map(int,re.findall(rb'DESKTOP_SAMPLE pages=(\d+)',g.output)))
  report['sampled_threads']=list(map(int,re.findall(rb'DESKTOP_SAMPLE[^\n]*threads=(\d+)',g.output)))
  report['visual_cache_bytes']=list(map(int,re.findall(rb'AURORA_DESKTOP_CACHE bytes=(\d+)',g.output)))
  (out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
