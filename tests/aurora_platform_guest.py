#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded real-guest render/SSG observations; host mock proposes, never grants."""
import argparse,hashlib,json,re,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
p=argparse.ArgumentParser()
for n in ('image','target','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--apps',type=Path)
p.add_argument('--case',choices=['render','semantic','notes','browser','dash'],required=True)
p.add_argument('--dash',type=Path)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
report={'status':'FAILED','case':a.case,'image_sha256':sha(a.image),'checks':[],'screenshots':{},'runs':[]};g=None
all_targets={'render':a.target/'render/render.elf','semantics':a.target/'semantics/semantics.elf','desktop':a.target/'desktop/desktop.elf','session':a.target/'session.elf','gap':a.target/'compositor_gap.elf'}
if a.apps:all_targets.update(notes=a.apps/'notes/notes.elf',browser=a.apps/'browser/browser.elf')
needed={'render':['render'],'semantic':['semantics'],'notes':['notes'],'browser':['browser'],'dash':['desktop','semantics','session','gap']}[a.case]
if any(n not in all_targets for n in needed):p.error('this case requires --apps')
payloads={n:all_targets[n] for n in needed}
for f in payloads.values():
 r=json.loads(f.with_suffix('.receipt.json').read_text());assert sha(f)==r['elf_sha256']
 for name,h in r['inputs'].items():assert sha(name)==h,name
report['elf_sha256']={n:sha(f) for n,f in payloads.items()}
def mark(name,**kw):report['checks'].append({'name':name,'status':'PASSED',**kw});print(name,'PASSED',flush=True)
def key(k,d):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':d,'key':{'type':'qcode','data':k}}}]})
def stroke(k):key(k,True);key(k,False);pump(g,.035)
def chord(mod,k):key(mod,True);stroke(k);key(mod,False);pump(g,.15)
def type_text(text):
 normal={'/':'slash','.':'dot','-':'minus',' ':'spc','\n':'ret',',':'comma','=':'equal','[':'bracket_left',']':'bracket_right',"'":'apostrophe',';':'semicolon'}
 shifted={'{':'bracket_left','}':'bracket_right',':':'semicolon','"':'apostrophe','_':'minus','(':'9',')':'0'}
 for c in text:
  shift=c in shifted or c.isupper()
  if shift:key('shift',True)
  stroke(shifted.get(c,normal.get(c,c.lower())))
  if shift:key('shift',False)
def click_xy(x,y):
 for _ in range(10):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-100}},{'type':'rel','data':{'axis':'y','value':-100}}]});pump(g,.02)
 for offset in range(0,max(x,y),80):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':min(80,max(0,x-offset))}},{'type':'rel','data':{'axis':'y','value':min(80,max(0,y-offset))}}]});pump(g,.02)
 for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':down}}]});pump(g,.1)
def point(pattern):return tuple(map(int,list(re.finditer(pattern,bytes(g.output)))[-1].groups()))
def shot(name):
 pump(g,.6);start=time.monotonic();g.qmp('screendump',{'filename':str(out/(name+'.ppm'))});from PIL import Image
 Image.open(out/(name+'.ppm')).save(out/(name+'.png'));report['screenshots'][name]={'sha256':sha(out/(name+'.png')),'png_bytes':(out/(name+'.png')).stat().st_size,'host_capture_ms':(time.monotonic()-start)*1000}
def latest(marker,start=0):
 deadline=time.monotonic()+30
 while time.monotonic()<deadline:
  data=re.findall(re.escape(marker)+rb' ([^\r\n]+)\r?\n',bytes(g.output)[start:])
  if data:return json.loads(data[-1])
  pump(g,.05)
 raise AssertionError('incomplete framed JSON: '+marker.decode())
def snapshot(kind):
 start=len(g.output);chord('ctrl','i');g.expect(b'SSG_'+kind+b'_DIFF ',start=start,timeout=30);pump(g,.2)
 return latest(b'SSG_'+kind+b'_SNAPSHOT',start),latest(b'SSG_'+kind+b'_DIFF',start)
try:
 with tempfile.TemporaryDirectory(prefix='xos_aurora_platform_') as tmp:
  disk=Path(tmp)/'work.img';create_fat32(disk,512)
  for name in ('/bin','/web'):transfer(disk,'mkdir',name)
  for name,f in payloads.items():transfer(disk,'import','/bin/'+name+'.elf',f)
  for f in (ROOT/'src/ports/aurora_browser/pages').iterdir():transfer(disk,'import','/web/'+f.name,f)
  fixtures={'ssg.txt':('Visible note title\n'+''.join(f'Line {i:03d}: native document semantics.\n' for i in range(80))).encode(),
   'ssg.html':b'<html><head><title>SSG fixture</title><style>body { margin:0; padding:16px; background:#f4f7fc; color:#23344e; font-size:16px; } .hidden { display:none; } .spacer { height:700px; }</style></head><body><h1>Visible Alpha</h1><a href="start.html">Native link target</a><div class="hidden"><p>HIDDEN_SECRET_FIXTURE</p></div><div class="spacer"></div><p>Below viewport omega</p><a href="garden.html">Bottom link</a></body></html>',
   'unsupported.html':b'<html><body><canvas>not a semantic model</canvas></body></html>'}
  for name,data in fixtures.items():f=Path(tmp)/name;f.write_bytes(data);transfer(disk,'import',('/web/' if name.endswith('.html') else '/')+name,f)
  if a.dash:
   transfer(disk,'import','/bin/dash',a.dash)
   script=Path(tmp)/'check.sh';script.write_text('/bin/desktop.elf\necho DESKTOP_DASH_STATUS:$?\n/bin/semantics.elf\necho SEMANTIC_DASH_STATUS:$?\n/bin/gap.elf\necho GAP_DASH_STATUS:$?\n/bin/session.elf\necho SESSION_DASH_STATUS:$?\n')
   transfer(disk,'import','/check.sh',script)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);base=resources(g)
  service_result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',service_result)[1]);g.expect(b'[display-service] ready');active=resources(g)
  def launch(name,args='',ready=None):
   b=len(g.output);send_bytes(g,f'exec-file /bin/{name}.elf {args}\r'.encode());g.expect(ready or (name.upper()+'_READY').encode(),start=b,timeout=90);pump(g,.4);return b
  def finish(b):stroke('esc');g.expect(b'kind=exited code=0',start=b,timeout=40);g.expect_supervisor(start=b);assert resources(g)==active
  if a.case=='render':
   for i,mode in enumerate(['high','balanced','low','safe','off','budget','opaque','balanced','opaque','balanced','opaque']):
    b=launch('render',mode);ready=re.search(rb'RENDER_READY mode=\w+ requested=(\d+) effective=(\d+) fallback=(\d+) bytes=(\d+) cache_ns=(\d+) generations=(\d+) pages=(\d+) threads=(\d+)',bytes(g.output)[b:]);assert ready
    row=dict(zip(['requested','effective','fallback','cache_bytes','cache_ns','generations','sampled_pages','sampled_threads'],map(int,ready.groups())));row.update(mode=mode,index=i)
    sb=len(g.output)
    for _ in range(16):stroke('a')
    g.expect(b'RENDER_EDIT count=16 ',start=sb);pump(g,.2);data=bytes(g.output)[sb:]
    gens=list(map(int,re.findall(rb'RENDER_EDIT[^\n]* generations=(\d+)',data)));assert gens and all(v==row['generations'] for v in gens)
    row['input_delivery_ns']=[int(y)-int(x) for x,y in re.findall(rb'\[qpa-input\][^\n]* ns=(\d+) kind=1 [^\n]* gui_ns=(\d+)',data)]
    row['dirty_present_ns']=list(map(int,re.findall(rb'\[qpa-frame\][^\n]* ns=(\d+)',data)))
    updates=re.findall(rb'RENDER_UPDATE_BEGIN\r?\n(.*?)RENDER_UPDATE_END ns=(\d+)',data,re.S)
    row['widget_update_paint_and_present_ns']=[int(ns) for body,ns in updates if b'[qpa-frame]' in body]
    assert row['widget_update_paint_and_present_ns'],'no synchronous paint/present update was measured'
    idle=len(g.output);pump(g,1.0);row['idle_flushes_1s']=bytes(g.output)[idle:].count(b'[qpa-flush]')
    shot('render-'+str(i)+'-'+mode);finish(b);report['runs'].append(row);mark('render_'+str(i)+'_'+mode)
   assert next(x for x in report['runs'] if x['mode']=='budget')['effective']==3
   assert next(x for x in report['runs'] if x['mode']=='budget')['cache_bytes']==0
   mark('budget_denial_safe_fallback_no_cache_rebuild_on_typing')
  elif a.case=='semantic':
   b=launch('semantics',ready=b'SEMANTIC_READY');data=bytes(g.output)[b:];assert b'=FAIL' not in data
   checks=re.findall(rb'SEMANTIC_CHECK ([^\r\n]+)=PASS',data);assert len(checks)>=19
   snapshot_data=latest(b'SSG_AGENT_SNAPSHOT',b);(out/'snapshot.json').write_text(json.dumps(snapshot_data,indent=2)+'\n')
   mock=subprocess.run([sys.executable,ROOT/'tests/mock_semantic_agent.py'],input=json.dumps(snapshot_data),text=True,capture_output=True,check=True)
   proposal=mock.stdout.strip();(out/'proposal.json').write_text(proposal+'\n');mark('independent_mock_selects_real_ssg_target',native_checks=len(checks))
   click_xy(*point(rb'SEMANTIC_POINT name=proposal xy=(\d+),(\d+)'));type_text(proposal)
   sb=len(g.output);click_xy(*point(rb'SEMANTIC_POINT name=authorize xy=(\d+),(\d+)'))
   g.expect(b'SEMANTIC_EXECUTE VERIFIED_LOCAL value=mock-agent-verified replay=DENIED',start=sb,timeout=30);g.expect(b'SEMANTIC_WITHOUT_GRANT DENIED',start=sb)
   result=latest(b'SSG_AGENT_RESULT',sb);assert any(n.get('nativeName')=='draft-title' and n.get('text')=='mock-agent-verified' for n in result['nodes'])
   shot('semantic-authorized-local-result');mark('query_propose_explicit_fixture_authorize_execute_verify');finish(b);mark('semantic_app_exact_resource_return')
   restart=len(g.output);send_bytes(g,b'spawn-file /bin/semantics.elf\r');g.expect(b'SEMANTIC_READY',start=restart,timeout=90);pump(g,.4)
   pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[restart:])[1])
   click_xy(*point(rb'SEMANTIC_POINT name=proposal xy=(\d+),(\d+)'));type_text(proposal)
   sb=len(g.output);click_xy(*point(rb'SEMANTIC_POINT name=authorize xy=(\d+),(\d+)'));g.expect(b'SEMANTIC_REJECT WRONG_SCOPE',start=sb)
   command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed');assert resources(g)==active
   mark('old_process_reference_refused_and_killed_ssg_resources_restored')
   projection=[{k:n[k] for k in ('role','name','enabled') if k in n} for n in snapshot_data['nodes']]
   report['coverage_comparison']={'ssg_json_bytes':len(json.dumps(snapshot_data).encode()),'ax_style_projection_bytes':len(json.dumps(projection).encode()),'ax_style_scope':'projection from Qt metadata, not a qualified XOS AX service','mock_target_success':'1/1 controlled target','screenshot_ocr':'NOT_RUN','cross_process_agent_execution':'BLOCKED / NOT_RUN'}
  elif a.case=='notes':
   b=launch('notes','/ssg.txt --ssg-probe',b'QT_EDITOR_READY');first=latest(b'SSG_NOTES_SNAPSHOT',b);assert first['status']=='OK'
   docs=[n for n in first['nodes'] if n['role']=='document'];assert docs and docs[0]['text'].startswith('Visible note title') and docs[0]['textScope']=='document-not-all-visible'
   same,delta=snapshot(b'NOTES');assert same['sceneVersion']==first['sceneVersion'] and delta['changed']==[];mark('notes_real_tree_text_and_readonly_query')
   stroke('a');changed,delta=snapshot(b'NOTES');assert delta['status']=='OK' and delta['changed'];assert any(n.get('nativeName')=='document' and n.get('text','').startswith('aVisible') for n in changed['nodes']);mark('notes_actual_edit_incremental_diff')
   chord('ctrl','a');selected,_=snapshot(b'NOTES');assert any(n.get('role')=='document' and n.get('selectionEnd',0)>n.get('selectionStart',0) for n in selected['nodes']);chord('ctrl','end');scrolled,_=snapshot(b'NOTES');assert any(n.get('role')=='document' and n.get('scrollY',0)>0 for n in scrolled['nodes']);mark('notes_selection_scroll_and_document_scope')
   for name,value in [('first',first),('changed',changed),('scrolled',scrolled)]: (out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
   shot('notes-scrolled');stroke('esc');g.expect(b'EDITOR_UNSAVED_GUARD',start=b);pump(g,.3);click_xy(*point(rb'EDITOR_POINT discard=(\d+),(\d+)'));g.expect(b'kind=exited code=0',start=b);g.expect_supervisor(start=b);assert resources(g)==active;mark('notes_ssg_exit_exact_resources')
  elif a.case=='browser':
   b=launch('browser','--ssg-probe',b'BROWSER_READY')
   def check_fragments(scene):
    vx,vy,vw,vh=scene['metadata']['viewport']
    for node in scene['nodes']:
     expected=[]
     for x,y,w,h in node['fragments']:
      x0,y0=max(x,vx),max(y,vy);x1,y1=min(x+w,vx+vw),min(y+h,vy+vh)
      if x1>x0 and y1>y0:expected.append([x0,y0,x1-x0,y1-y0])
     assert node['visibleFragments']==expected
     if node['visibility'] in ('viewport-visible','viewport-partial','viewport-visible-fragments-incomplete'):assert expected
     if node['visibility'] in ('not-rendered','scroll-required','UNKNOWN_FRAGMENT_TRUNCATED'):assert not expected
   def navigate(path,expected=None):
    sb=len(g.output);chord('ctrl','l');type_text(path);stroke('ret');g.expect(expected or b'BROWSER_LOADED path='+path.encode(),start=sb,timeout=30);pump(g,.3)
   navigate('/web/ssg.html');first,_=snapshot(b'BROWSER');assert first['status']=='OK';check_fragments(first)
   texts=[n for n in first['nodes'] if n.get('role')=='text'];assert 'Visible' in ''.join(n.get('text','') for n in texts)
   hidden=[n for n in texts if 'HIDDEN_SECRET' in n.get('text','')];assert hidden and all(n['visibility']=='not-rendered' for n in hidden)
   assert any(n['visibility']=='scroll-required' for n in first['nodes']);mark('browser_dom_layout_hidden_and_offviewport')
   link=next(n for n in first['nodes'] if n.get('href')=='start.html');assert link['fragments'] and link['visibility'].startswith('viewport')
   x,y,w,h=link['fragments'][0];shot('browser-dom-first');click_xy(x+min(8,w//2),y+min(8,h//2));g.expect(b'BROWSER_LOADED path=/web/start.html',start=b);mark('ssg_link_geometry_matches_actual_engine_hit')
   navigate('/web/ssg.html');again,_=snapshot(b'BROWSER');assert again['sourceEpoch']!=first['sourceEpoch'];stroke('end');bottom,delta=snapshot(b'BROWSER');assert bottom['sourceEpoch']==again['sourceEpoch'] and delta['status']=='OK'
   check_fragments(bottom);assert delta['metadata']['scrollY']>0 and delta['capped']==False
   assert any(n.get('text','').find('Below')>=0 and n['visibility'].startswith('viewport') for n in bottom['nodes']);mark('browser_scroll_changes_visibility_with_stable_epoch')
   sb=len(g.output);chord('ctrl','r');g.expect(b'BROWSER_LOADED path=/web/ssg.html',start=sb);reload,diff=snapshot(b'BROWSER');assert reload['sourceEpoch']!=bottom['sourceEpoch'] and diff['status']=='SOURCE_REPLACED';mark('reload_invalidates_old_document_references')
   navigate('/web/unsupported.html',b'Unsupported HTML tag');retained,_=snapshot(b'BROWSER');assert retained['sourceEpoch']==reload['sourceEpoch'];mark('unsupported_canvas_rejected_no_fabricated_semantics')
   for name,value in [('first',first),('bottom',bottom),('reload',reload),('reload-diff',diff)]: (out/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
   shot('browser-dom-reload');finish(b);mark('browser_ssg_exit_exact_resources')
  else:
   assert a.dash
   b=len(g.output);send_bytes(g,b'exec-driver /bin/dash /check.sh\r');g.expect(b'DESKTOP_READY',start=b,timeout=90);chord('ctrl','q');g.expect(b'DESKTOP_DASH_STATUS:0',start=b);g.expect(b'SEMANTIC_READY',start=b,timeout=90);stroke('esc');g.expect(b'SEMANTIC_DASH_STATUS:0',start=b);g.expect(b'GAP_DASH_STATUS:0',start=b);g.expect(b'SESSION_START_FAILED error=-1',start=b);g.expect(b'SESSION_DASH_STATUS:1',start=b);g.expect_supervisor(start=b,timeout=40);assert resources(g)==active;mark('dash_real_desktop_and_semantic_elf_lifecycle')
  command(g,'exec gfxdemo stop',b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base;command(g,'sync',b'[files] sync=ok');mark('serial_file_service_and_resource_baseline');report['status']='PASSED'
except Exception as error:report['error']=repr(error);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
