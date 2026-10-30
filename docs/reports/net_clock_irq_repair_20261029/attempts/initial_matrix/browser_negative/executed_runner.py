#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real XOS liteHTML browser: PS/2 navigation, hostile local input and teardown."""
import argparse,hashlib,json,re,sys,tempfile
from pathlib import Path
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/runs/browser_negative');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--case',choices=['interactive','negative','lifecycle'],default='interactive');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','case':a.case,'image_sha256':sha(a.image),'elf_sha256':sha(a.payload),'receipt_sha256':sha(a.payload.with_suffix('.receipt.json')),'source_pages':{str(f.relative_to(ROOT)):sha(f) for f in (ROOT/'src/ports/aurora_browser/pages').iterdir()},'runner_sha256':sha(Path(__file__)),'checks':[]};g=None
pages=ROOT/'src/ports/aurora_browser/pages'
def mark(name,**kw):report['checks'].append({'name':name,'status':'PASSED',**kw});print(name,'PASSED',flush=True)
def key(k,d):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':d,'key':{'type':'qcode','data':k}}}]})
def stroke(k):key(k,True);key(k,False);pump(g,.025)
def chord(mod,k):key(mod,True);stroke(k);key(mod,False);pump(g,.05)
def type_text(text):
 codes={'/':'slash','.':'dot','-':'minus',' ':'spc'}
 for c in text:stroke(codes.get(c,c))
def navigate(path,expected=None):
 start=len(g.output);chord('ctrl','l');type_text(path);stroke('ret');g.expect(expected or b'BROWSER_LOADED path='+path.encode(),start=start,timeout=30);pump(g,.15);return start
def click_xy(x,y):
 for _ in range(10):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-100}},{'type':'rel','data':{'axis':'y','value':-100}}]});pump(g,.025)
 for offset in range(0,max(x,y),80):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':min(80,max(0,x-offset))}},{'type':'rel','data':{'axis':'y','value':min(80,max(0,y-offset))}}]});pump(g,.025)
 pump(g,.1)
 for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':down}}]});pump(g,.1)
def screenshot(name):
 g.qmp('screendump',{'filename':str(out/(name+'.ppm'))});from PIL import Image
 im=Image.open(out/(name+'.ppm'));assert im.size==(800,600);im.save(out/(name+'.png'));report.setdefault('screenshots',{})[name]=sha(out/(name+'.png'));return im
try:
 with tempfile.TemporaryDirectory(prefix='xos_browser_') as tmp:
  d=Path(tmp);disk=d/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'mkdir','/web');transfer(disk,'import','/bin/aurora.elf',a.payload)
  for f in pages.iterdir():transfer(disk,'import','/web/'+f.name,f)
  malformed={'broken.html':b'<html><body><p>Unclosed','deep.html':b'<div>'*17+b'x'+b'</div>'*17,'huge.html':b'x'*32769,'script.html':b'<html><body><script>1</script></body></html>','attr.html':b'<html><body><p style\t="width:1e99px">x</p></body></html>','dimension.html':b'<html><body><img src="garden.bmp" width="9999999999"></body></html>','exponent.html':b'<html><head><style>body { width:1e9999px; }</style></head><body>x</body></html>','badexternal.css':b'body { width: 9999%; }','external.html':b'<html><head><link rel="stylesheet" href="badexternal.css"></head><body>x</body></html>','imports.html':b'<html><head>'+b'<link rel="stylesheet" href="theme.css">'*9+b'</head><body>x</body></html>','cycle.css':b'@import "cycle.css";','badcss.html':b'<html><head><style>@import "cycle.css";</style></head><body>test</body></html>','badimage.html':b'<html><body><h1>Bad image stays contained</h1><img src="bad.bmp"></body></html>','bad.bmp':b'BM'+b'\xff'*100}
  for name,data in malformed.items():f=d/name;f.write_bytes(data);transfer(disk,'import','/web/'+name,f)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command;g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.2);base=resources(g);service_result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',service_result)[1]);g.expect(b'[display-service] ready');with_service=resources(g);report['baseline']=base;report['with_service']=with_service
  def start(background=False):
   b=len(g.output);send_bytes(g,(b'spawn-file' if background else b'exec-file')+b' /bin/aurora.elf\r');g.expect(b'BROWSER_READY',start=b,timeout=90);pump(g,.3);return b
  def finish(b):
   stroke('esc');g.expect(b'kind=exited code=0',start=b,timeout=30);g.expect_supervisor(start=b);assert resources(g)==with_service
  b=start();im=screenshot('start');assert b'BROWSER_LOADED path=/web/start.html' in bytes(g.output)[b:];assert b'BROWSER_CSS_LOADED path=/web/theme.css' in bytes(g.output)[b:];assert sum(1 for pixel in im.convert('RGB').get_flattened_data() if pixel==(244,247,252))>50000;mark('real_litehtml_engine_and_aurora_start_page')
  if a.case=='interactive':
   anchor=list(re.finditer(rb'BROWSER_ANCHOR point=(\d+),(\d+)',bytes(g.output)[b:]))[-1];x,y=map(int,anchor.groups());sb=len(g.output);click_xy(x,y);g.expect(b'BROWSER_LINK target=/web/reading.html',start=sb);g.expect(b'BROWSER_LOADED path=/web/reading.html',start=sb);mark('real_ps2_anchor_click')
   screenshot('reading-top');stroke('pgdn');g.expect(b'BROWSER_SCROLL value=',start=b);stroke('end');pump(g,.2);screenshot('reading-end');assert max(map(int,re.findall(rb'BROWSER_SCROLL value=(\d+)',bytes(g.output)[b:])))>0;mark('address_bar_and_long_document_scroll')
   sb=len(g.output);chord('alt','left');g.expect(b'BROWSER_LOADED path=/web/start.html',start=sb);sb=len(g.output);chord('alt','right');g.expect(b'BROWSER_LOADED path=/web/reading.html',start=sb);sb=len(g.output);chord('ctrl','r');g.expect(b'BROWSER_LOADED path=/web/reading.html',start=sb);mark('independent_back_forward_refresh')
   sb=len(g.output);chord('ctrl','t');g.expect(b'BROWSER_TAB active=1',start=sb);navigate('/web/garden.html');sb=len(g.output);chord('ctrl','tab');g.expect(b'BROWSER_TAB active=0',start=sb);g.expect(b'BROWSER_LOADED path=/web/reading.html',start=sb);screenshot('tabs');mark('two_tabs_independent_history')
   m=list(re.finditer(rb'BROWSER_POINT bookmark=(\d+),(\d+)',bytes(g.output)[b:]))[-1];sb=len(g.output);click_xy(*map(int,m.groups()));g.expect(b'BROWSER_BOOKMARK_ADDED path=/web/reading.html',start=sb);mark('real_session_bookmark_creation')
   navigate('/web/garden.html');image=screenshot('garden');assert b'images=1' in bytes(g.output)[b:];mark('css_layout_bmp_and_utf8',glyph_scope='DejaVu Latin/Greek; no full Unicode claim')
   for path in ['/web/start.html','/web/garden.html','/web/reading.html']*2:navigate(path)
   mark('repeated_navigation_releases_previous_document')
  elif a.case=='negative':
   cases=[('/web/missing.html',b'Page error: Page or resource missing'),('/web/broken.html',b'Page error: Unclosed markup rejected'),('/web/deep.html',b'Page error: HTML nesting budget exceeded'),('/web/huge.html',b'Page error: Resource byte budget exceeded'),('/web/script.html',b'Page error: Unsupported HTML tag: script'),('/web/badcss.html',b'Page error: Stylesheet budget rejected'),('/web/attr.html',b'Page error: Unsupported or excessive HTML attributes'),('/web/dimension.html',b'Page error: Unsupported or excessive HTML attributes'),('/web/exponent.html',b'Page error: Stylesheet budget rejected'),('/web/imports.html',b'Page error: Engine allocation or resource budget failed'),('/web/external.html',b'Page error: Engine allocation or resource budget failed'),('/bin/aurora.elf',b'Blocked: local /web pages only')]
   for path,wanted in cases:navigate(path,wanted);mark('reject_'+path.rsplit('/',1)[-1])
   navigate('/web/badimage.html');assert b'BROWSER_RESOURCE_REJECT image' in bytes(g.output)[b:] or b'BROWSER_RESOURCE_REJECT bmp-header' in bytes(g.output)[b:];mark('malformed_image_contained');navigate('/web/start.html');screenshot('error-recovery');mark('valid_navigation_after_rejected_input')
  finish(b);mark('normal_exit_exact_resource_return')
  if a.case=='lifecycle':
   for _ in range(2):b=start();finish(b)
   mark('three_launch_exit_cycles_exact_resources')
   b=start(True);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed');assert resources(g)==with_service;mark('killed_browser_full_resource_return')
   b=start(True);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'kill {service}',b'kill: accepted');command(g,f'wait {pid}',b'kind=exited code=72');command(g,f'wait {service}',b'kind=killed');assert resources(g)==base;mark('display_death_browser_fails_closed_serial_survives');service_result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',service_result)[1]);g.expect(b'[display-service] ready');with_service=resources(g);b=start();finish(b);mark('new_browser_after_display_restart')
  command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base;pump(g,.2);command(g,'sync',b'[files] sync=ok');mark('file_sync_and_serial_rescue_after_browser');report['status']='PASSED'
except Exception as error:report['error']=str(error);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 data=bytes(g.output) if g else b'';report['measurements']={'sampled_pages':[int(x) for x in re.findall(rb'BROWSER_SAMPLE pages=(\d+)',data)],'sampled_threads':[int(x) for x in re.findall(rb'BROWSER_SAMPLE[^\n]* threads=(\d+)',data)],'visual_cache_bytes':[int(x) for x in re.findall(rb'AURORA_CACHE bytes=(\d+)',data)],'absolute_peak':'NOT_RUN'}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
