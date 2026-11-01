#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise prewired independent XOS Notes and read-only consumer processes."""
import argparse,base64,hashlib,json,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command,resources
from task_smoke import send_bytes,pump
p=argparse.ArgumentParser()
for n in ('image','session','consumer','notes','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--browser',type=Path)
p.add_argument('--dash',type=Path)
p.add_argument('--only-browser',action='store_true')
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
if a.only_browser and not a.browser:p.error('--only-browser requires --browser')
sha=lambda data:hashlib.sha256(data).hexdigest()
report={'status':'FAILED','inputs':{n:{'path':str(getattr(a,n).resolve()),'sha256':sha(getattr(a,n).read_bytes())} for n in ('image','session','consumer','notes')},'checks':[]}
g=None
def mark(name):report['checks'].append(name);print('PASS',name,flush=True)
def key(k,down):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':k}}}]})
def stroke(k):key(k,True);key(k,False);pump(g,.1)
def click_xy(x,y):
 for _ in range(10):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':-100}},{'type':'rel','data':{'axis':'y','value':-100}}]});pump(g,.02)
 for offset in range(0,max(x,y),80):g.qmp('input-send-event',{'events':[{'type':'rel','data':{'axis':'x','value':min(80,max(0,x-offset))}},{'type':'rel','data':{'axis':'y','value':min(80,max(0,y-offset))}}]});pump(g,.02)
 for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'btn','data':{'button':'left','down':down}}]});pump(g,.1)
def extract_frames(data):
 frames={}
 for direction,seq,size,encoded_size in re.findall(rb'SSG_FRAME_BEGIN (REQ|RESP) (\d+) (\d+) (\d+)',data):
  seq=int(seq);key=(direction.decode(),seq);parts={int(offset):chunk for offset,chunk in re.findall(rb'SSG_FRAME_PART '+direction+rb' '+str(seq).encode()+rb' (\d+) ([A-Za-z0-9+/=]+)',data)}
  joined=b''.join(parts[i] for i in sorted(parts))
  if len(joined)!=int(encoded_size):raise AssertionError(f'incomplete log frame {key}: {len(joined)}/{encoded_size!r}')
  payload=base64.b64decode(joined,validate=True)
  if len(payload)!=int(size):raise AssertionError(f'frame length mismatch {key}')
  frames[key]=payload
 return frames
try:
 with tempfile.TemporaryDirectory(prefix='xos_ssg_ipc_') as tmp:
  tmp=Path(tmp);disk=tmp/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin')
  for src,dest in ((a.session,'session'),(a.consumer,'ssg-consumer'),(a.notes,'notes')):transfer(disk,'import','/bin/'+dest+'.elf',src)
  if a.browser:
   report['inputs']['browser']={'path':str(a.browser.resolve()),'sha256':sha(a.browser.read_bytes())}
   transfer(disk,'import','/bin/browser.elf',a.browser);transfer(disk,'mkdir','/web')
   page=tmp/'ssg.html'
   page.write_text('<html><head><title>IPC fixture</title><style>body { margin:0; padding:16px; } .spacer { height:900px; }</style></head><body><h1>Visible Alpha</h1><a href="ssg.html">Native link target</a><div class="spacer"></div><p>Below viewport omega</p></body></html>')
   transfer(disk,'import','/web/ssg.html',page)
  if a.dash:
   report['inputs']['dash']={'path':str(a.dash.resolve()),'sha256':sha(a.dash.read_bytes())}
   transfer(disk,'import','/bin/dash',a.dash)
   script=tmp/'ssg-dash.sh';script.write_text('/bin/session.elf /ssg.txt scenario --text\necho SSG_DASH_STATUS:$?\n')
   transfer(disk,'import','/ssg-dash.sh',script)
  note=tmp/'ssg.txt';note.write_text('Visible note title\n' + ''.join(f'Line {i:03d}: native document semantics.\n' for i in range(80)))
  transfer(disk,'import','/ssg.txt',note)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=45)
  command(g,'demo quiet',b'demo tasks stopped');base=resources(g)
  service_result=command(g,'display-start',b'result=0');service=int(re.search(rb'\[display-start\] pid=(\d+)',service_result)[1]);g.expect(b'[display-service] ready');active=resources(g)
  report['baseline_resources']=base;report['display_resources']=active
  if not a.only_browser:
   start=len(g.output);line='exec-driver /bin/session.elf /ssg.txt scenario --text';report['guest_command']=line;send_bytes(g,(line+'\r').encode())
   marker=g.expect_any((b'SSG_CONSUMER_HOLD_READ',b'SSG_CONSUMER_TRANSPORT',b'SSG_SESSION consumer_wait='),start=start,timeout=120)
   if marker!=b'SSG_CONSUMER_HOLD_READ':raise AssertionError('consumer failed before backpressure: '+marker.decode())
   g.expect(b'SSG_PIPE_BACKPRESSURE',start=start,timeout=20);stroke('left');g.expect(b'EDITOR_KEY',start=start,timeout=20)
   mark('gui_input_remains_responsive_under_pipe_backpressure')
   g.expect(b'SSG_CONSUMER_WAIT_EDIT',start=start,timeout=40)
   pump(g,.5);stroke('a');g.expect(b'EDITOR_CHANGE',start=start,timeout=20)
   g.expect(b'SSG_CONSUMER_WAIT_SCROLL',start=start,timeout=90)
   key('ctrl',True);stroke('end');key('ctrl',False)
   g.expect(b'SSG_CONSUMER_DONE failures=0 waiting_for_provider_exit=1',start=start,timeout=90)
   stroke('esc');g.expect(b'EDITOR_UNSAVED_GUARD',start=start,timeout=30);g.expect(b'EDITOR_POINT discard=',start=start,timeout=20)
   m=list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)',bytes(g.output)[start:]))[-1];click_xy(*map(int,m.groups()))
   g.expect(b'SSG_CONSUMER_EXIT failures=0',start=start,timeout=60);g.expect(b'SSG_SESSION provider_wait=',start=start,timeout=60);g.expect_supervisor(start=start,timeout=60)
   output=bytes(g.output)[start:];(out/'scenario.serial.log').write_bytes(output)
   match=re.search(rb'SSG_SESSION parent=(\d+) provider=(\d+) consumer=(\d+) instance=([0-9a-f]{32})',output)
   if not match:raise AssertionError('missing parent spawn identity record')
   parent,provider,consumer=map(int,match.groups()[:3]);instance=match.group(4).decode();report['processes']={'parent_pid':parent,'provider_pid':provider,'consumer_pid':consumer,'instance':instance}
   assert len({parent,provider,consumer})==3
   assert re.search(rb'SSG_PROVIDER_READY pid='+str(provider).encode()+rb' instance='+instance.encode(),output)
   assert re.search(rb'SSG_CONSUMER_START pid='+str(consumer).encode(),output)
   assert re.search(rb'SSG_PIPE_BACKPRESSURE pid='+str(provider).encode(),output)
   assert output.index(b'SSG_PIPE_BACKPRESSURE')<output.index(b'EDITOR_KEY')<output.index(b'SSG_CONSUMER_WAIT_EDIT')
   mark('separate_processes_bound_by_parent')
   checks=re.findall(rb'SSG_CONSUMER_CHECK ([a-z_]+)=(PASS|FAIL)',output)
   report['consumer_checks']=[{'name':n.decode(),'status':s.decode()} for n,s in checks]
   if len(checks)<12 or any(s!=b'PASS' for _,s in checks):raise AssertionError('consumer checks incomplete or failed: '+str(checks))
   mark('consumer_parsed_live_notes_and_failure_semantics')
   frames=extract_frames(output);report['frames']=[]
   for (direction,seq),payload in sorted(frames.items(),key=lambda x:(x[0][1],x[0][0])):
    path=out/f'{seq:02d}-{direction.lower()}.json';path.write_bytes(payload)
    parsed=json.loads(payload);report['frames'].append({'direction':direction,'sequence':seq,'bytes':len(payload),'sha256':sha(payload),'file':path.name,'op':parsed.get('op'),'status':parsed.get('status')})
   assert len(frames[('RESP',2)])>4096
   first=json.loads(frames[('RESP',3)]);delta=json.loads(frames[('RESP',4)]);after=json.loads(frames[('RESP',5)])
   assert first['providerPid']==str(provider) and first['sourceInstance']==instance
   before_node=next(x for x in first['nodes'] if x.get('nativeName')=='document');after_node=next(x for x in after['nodes'] if x.get('nativeName')=='document')
   assert before_node['text'].startswith('Visible note title') and after_node['text'].startswith('aVisible note title')
   assert before_node['bounds'][2]>0 and before_node['bounds'][3]>0 and delta['status']=='OK' and delta['changed']
   mark('recorded_real_keyboard_edit_and_consumer_diff')
   assert resources(g)==active;mark('both_children_and_pipe_resources_reclaimed')
   # A later provider process must reject the exact reference from the first.
   b=len(g.output)
   oldref=(f"exec-driver /bin/session.elf /ssg.txt ref-detail {instance} "
           f"{first['sourceEpoch']} {first['sceneVersion']} document {before_node['id']} --text")
   send_bytes(g,(oldref+'\r').encode())
   g.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=1',start=b,timeout=100);g.expect(b'QT_EDITOR_READY',start=b,timeout=60)
   replaced_output=bytes(g.output)[b:];new_id=re.search(rb'SSG_SESSION parent=\d+ provider=\d+ consumer=\d+ instance=([0-9a-f]{32})',replaced_output)
   assert new_id and new_id.group(1).decode()!=instance
   replaced=extract_frames(replaced_output);replaced_scene=json.loads(replaced[('RESP',1)])
   assert replaced_scene['status']=='SOURCE_REPLACED' and replaced_scene['sourceInstance']==new_id.group(1).decode()
   (out/'old-provider-ref-request.json').write_bytes(replaced[('REQ',1)])
   (out/'old-provider-ref-response.json').write_bytes(replaced[('RESP',1)])
   stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('actual_provider_restart_rejects_old_node_reference')
   # With no --text, the same real document is observable only as metadata.
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt snapshot document\r')
   g.expect(b'SSG_SESSION consumer_wait=',start=b,timeout=100);g.expect(b'QT_EDITOR_READY',start=b,timeout=60)
   part=bytes(g.output)[b:];denied_frames=extract_frames(part);denied=json.loads(denied_frames[('RESP',1)])
   assert denied['status']=='OK' and any(n.get('role')=='document' and n.get('textStatus')=='NOT_AUTHORIZED' and 'text' not in n for n in denied['nodes'])
   stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   (out/'text-denied-response.json').write_bytes(denied_frames[('RESP',1)]);mark('text_scope_denied_by_default')
   # Exercise the ordinary CLI detail and diff modes within a single connection.
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt detail document --text\r')
   g.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=0',start=b,timeout=100);g.expect(b'QT_EDITOR_READY',start=b,timeout=60)
   detail_frames=extract_frames(bytes(g.output)[b:]);detail=json.loads(detail_frames[('RESP',2)])
   assert detail['status']=='OK' and detail['node']['nativeName']=='document'
   (out/'cli-detail-response.json').write_bytes(detail_frames[('RESP',2)])
   stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt diff document 5 --text\r')
   g.expect(b'SSG_WATCH_NEXT seconds=5',start=b,timeout=100);stroke('b');g.expect(b'EDITOR_CHANGE',start=b,timeout=20)
   g.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=0',start=b,timeout=60)
   diff_frames=extract_frames(bytes(g.output)[b:]);change=json.loads(diff_frames[('RESP',2)])
   assert change['status']=='OK' and any(n.get('text','').startswith('bVisible note title') for n in change['changed'])
   (out/'cli-diff-response.json').write_bytes(diff_frames[('RESP',2)])
   stroke('esc');g.expect(b'EDITOR_UNSAVED_GUARD',start=b,timeout=30);g.expect(b'EDITOR_POINT discard=',start=b,timeout=20)
   point=list(re.finditer(rb'EDITOR_POINT discard=(\d+),(\d+)',bytes(g.output)[b:]))[-1];click_xy(*map(int,point.groups()))
   g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('standalone_cli_detail_and_diff')
   # A peer that closes after a partial frame must be rejected, not parsed.
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt truncated --text\r')
   g.expect(b'SSG_PROVIDER_END',start=b,timeout=100);g.expect(b'SSG_CONSUMER_FAULT truncated_sent=1 result=EOF',start=b,timeout=60)
   assert b'reason=TRUNCATED' in bytes(g.output)[b:]
   g.expect(b'QT_EDITOR_READY',start=b,timeout=60);stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('truncated_frame_disconnect_and_cleanup')
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt oversize --text\r')
   g.expect(b'reason=LIMIT',start=b,timeout=100);g.expect(b'SSG_CONSUMER_FAULT oversized_header=1 result=EOF',start=b,timeout=60)
   g.expect(b'QT_EDITOR_READY',start=b,timeout=60);stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('oversized_frame_refused_and_cleanup')
   # No response eventually closes the consumer's own routes on a monotonic deadline.
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt timeout --text\r')
   g.expect(b'SSG_CONSUMER_FAULT idle_result=TIMEOUT',start=b,timeout=100);g.expect(b'QT_EDITOR_READY',start=b,timeout=60)
   stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('consumer_timeout_disconnect_and_cleanup')
   # A live peer that sends only a frame prefix must not pin the provider forever.
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /ssg.txt partial-timeout --text\r')
   g.expect(b'reason=TIMEOUT',start=b,timeout=100)
   g.expect(b'SSG_CONSUMER_FAULT partial_sent=1 result=EOF',start=b,timeout=60);g.expect(b'QT_EDITOR_READY',start=b,timeout=60)
   stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('provider_partial_frame_timeout_and_cleanup')
  if a.browser:
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /web/ssg.html browser-scenario --browser --text\r')
   g.expect(b'SSG_CONSUMER_WAIT_BROWSER_SCROLL',start=b,timeout=120);stroke('end')
   phase=g.expect_any((b'SSG_CONSUMER_WAIT_BROWSER_RETRY_SCROLL',b'SSG_CONSUMER_WAIT_BROWSER_RELOAD'),start=b,timeout=60)
   if phase==b'SSG_CONSUMER_WAIT_BROWSER_RETRY_SCROLL':stroke('home');g.expect(b'SSG_CONSUMER_WAIT_BROWSER_RELOAD',start=b,timeout=60)
   key('ctrl',True);stroke('r');key('ctrl',False)
   g.expect(b'SSG_CONSUMER_BROWSER_DONE failures=0',start=b,timeout=60)
   stroke('esc');g.expect(b'SSG_CONSUMER_BROWSER_EXIT failures=0',start=b,timeout=60);g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60)
   browser_output=bytes(g.output)[b:];browser_frames=extract_frames(browser_output)
   identity=re.search(rb'SSG_SESSION parent=(\d+) provider=(\d+) consumer=(\d+) instance=([0-9a-f]{32})',browser_output)
   if not identity:raise AssertionError('missing Browser process identities')
   bp,bprovider,bc=map(int,identity.groups()[:3]);browser_instance=identity.group(4).decode()
   assert len({bp,bprovider,bc})==3
   assert re.search(rb'SSG_PROVIDER_READY pid='+str(bprovider).encode()+rb' instance='+browser_instance.encode(),browser_output)
   assert re.search(rb'SSG_CONSUMER_START pid='+str(bc).encode(),browser_output)
   report['browser_processes']={'parent_pid':bp,'provider_pid':bprovider,'consumer_pid':bc,'instance':browser_instance}
   report['browser_frames']=[]
   for (direction,seq),payload in sorted(browser_frames.items()):
    name=f'browser-{seq:02d}-{direction.lower()}.json';(out/name).write_bytes(payload)
    report['browser_frames'].append({'direction':direction,'sequence':seq,'bytes':len(payload),'sha256':sha(payload),'file':name})
   pairs=[(json.loads(browser_frames[('REQ',seq)]),json.loads(browser_frames[('RESP',seq)]))
          for seq in sorted(n for direction,n in browser_frames if direction=='REQ')]
   scene=next(resp for req,resp in pairs if req.get('op')=='snapshot' and req.get('role')=='content' and resp.get('status')=='OK' and not resp.get('capped') and resp['metadata']['scrollY']==0)
   delta=next(resp for req,resp in pairs if req.get('op')=='diff' and resp.get('status')=='OK' and resp.get('changed'))
   replacement=next(resp for req,resp in pairs if req.get('op')=='diff' and resp.get('status')=='SOURCE_REPLACED')
   old_node=next(resp for req,resp in pairs if req.get('op')=='detail' and resp.get('status')=='SOURCE_REPLACED')
   visible_links=next(resp for req,resp in pairs if req.get('op')=='snapshot' and req.get('role')=='link' and req.get('visibleOnly'))
   assert scene['providerPid']==str(bprovider) and scene['sourceInstance']==browser_instance
   assert any(n.get('role')=='link' and n.get('href')=='ssg.html' and n.get('visibleFragments') for n in scene['nodes'])
   assert any(n.get('role')=='text' and 'Visible' in n.get('text','') for n in scene['nodes'])
   assert re.search(rb'BROWSER_SCROLL value=[1-9]\d*',browser_output) and delta['status']=='OK' and delta['changed']
   assert replacement['status']=='SOURCE_REPLACED' and old_node['status']=='SOURCE_REPLACED' and visible_links['status']=='OK'
   assert resources(g)==active;mark('browser_real_fragment_scroll_reload_and_stale_epoch')
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /web/ssg.html snapshot --browser content\r')
   g.expect(b'SSG_SESSION consumer_wait=0 outcome=1 code=1',start=b,timeout=100);g.expect(b'BROWSER_READY',start=b,timeout=60)
   blocked=extract_frames(bytes(g.output)[b:]);blocked_scene=json.loads(blocked[('RESP',1)])
   assert blocked_scene['status']=='DENIED' and 'nodes' not in blocked_scene
   (out/'browser-text-denied-response.json').write_bytes(blocked[('RESP',1)])
   stroke('esc');g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60);assert resources(g)==active
   mark('browser_text_scope_denied_by_default')
   # The legacy local probe cannot enable text for an unprivileged pipe.
   b=len(g.output);send_bytes(g,b'exec-driver /bin/session.elf /web/ssg.html browser-guard --browser --local-probe\r')
   g.expect(b'SSG_CONSUMER_WAIT_BROWSER_GUARD',start=b,timeout=120)
   key('ctrl',True);stroke('i');key('ctrl',False);g.expect(b'SSG_BROWSER_PROBE DENIED',start=b,timeout=30)
   g.expect(b'SSG_CONSUMER_BROWSER_GUARD_DONE failures=0',start=b,timeout=60)
   stroke('esc');g.expect(b'SSG_CONSUMER_BROWSER_GUARD_EXIT failures=0',start=b,timeout=60);g.expect(b'SSG_SESSION provider_wait=',start=b,timeout=60);g.expect_supervisor(start=b,timeout=60)
   guard_frames=extract_frames(bytes(g.output)[b:])
   assert json.loads(guard_frames[('RESP',1)])['status']=='DENIED' and json.loads(guard_frames[('RESP',2)])['status']=='DENIED'
   (out/'browser-guard-before.json').write_bytes(guard_frames[('RESP',1)]);(out/'browser-guard-after.json').write_bytes(guard_frames[('RESP',2)])
   assert resources(g)==active;mark('browser_local_probe_cannot_expand_pipe_text_scope')
  if a.dash:
   b=len(g.output);send_bytes(g,b'exec-driver /bin/dash /ssg-dash.sh\r')
   g.expect(b'SSG_SESSION consumer_spawn=FAIL code=-1',start=b,timeout=90);g.expect(b'SSG_DASH_STATUS:2',start=b,timeout=30)
   g.expect_supervisor(start=b,timeout=30);assert resources(g)==active;mark('dash_without_spawn_delegation_denied')
  command(g,'exec gfxdemo stop' ,b'kind=exited code=0');command(g,f'wait {service}',b'kind=exited code=0');assert resources(g)==base
  command(g,'sync',b'[files] sync=ok');report['final_resources']=resources(g);mark('display_and_guest_resource_baseline_restored')
  report['status']='PASSED_SCOPED'
except Exception as error:
 report['error']=repr(error);raise
finally:
 if g:g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
