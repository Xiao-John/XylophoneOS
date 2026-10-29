#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Guest FB1 generation, restart/export, and FB2 exact-symbol qualification."""
import hashlib,json,os,re,subprocess,sys,tempfile
from unittest.mock import patch
import boot_smoke
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from qt6_fat_fixture import alter
from fb2_symbolize import symbolize,validate,Invalid
from toolchain import COMMON_FLAGS,X86_FLAGS,tool
out=Path(os.environ.get('FB12_ACCEPTANCE',ROOT/'build/fb12/acceptance'));out.mkdir(parents=True,exist_ok=True);system=Path(os.environ.get('FB12_SYSTEM',ROOT/'build/fb12/system'));manifest=json.loads((system/'manifest.json').read_text())
for name,digest in manifest['sources'].items():
 if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise SystemExit('stale source '+name)
for name,info in manifest['artifacts'].items():
 if hashlib.sha256((system/name).read_bytes()).hexdigest()!=info['sha256']:raise SystemExit('changed artifact '+name)
fixture=ROOT/'tests/fixtures/fb12/fault_cases.cpp';sdk=system/'sdk';obj=out/'fault_cases.o';fixture_elf=out/'fault_cases.elf'
subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(fixture),'-o',str(obj)],check=True)
subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(obj),str(sdk/'lib/libxos.a'),'-o',str(fixture_elf)],check=True)
run=system/'user_fault.image.elf';symbols=system/'user_fault.elf';summary={'status':'failed','build_id':manifest['build_id'],'checks':[],'fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'fixture_elf_sha256':hashlib.sha256(fixture_elf.read_bytes()).hexdigest()};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_fb12_') as temp:
  tmp=Path(temp);disk=tmp/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/fault.elf',run);transfer(disk,'import','/bin/hello.elf',system/'user_hello.image.elf');transfer(disk,'import','/bin/fcases.elf',fixture_elf)
  def boot(name,cpu='qemu64,+rdrand'):
   global g
   g=Guest(system/'xos.img',str(out.relative_to(ROOT/'build'))+'/'+name,work_disk=disk,cpu=cpu);g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=45)
   command(g,'demo keep',b'demo: keep')
   for pid in (1,3,4):command(g,f'kill {pid}',b'kill: accepted')
   pump(g,.3)
  boot('first');baseline=resources(g);normal=command(g,'diag /bin/hello.elf',b'kind=exited code=0',timeout=90);assert b'[fault-bundle] saved' not in normal
  summary['checks'].append({'name':'normal_exit_has_no_fault_bundle'})
  case_paths={}
  for mode,vector in (('divide',0),('ud',6)):
   result=command(g,'diag /bin/fcases.elf '+mode,b'[fault-bundle] saved ',timeout=90)
   assert ('kind=faulted code=0 vector='+str(vector)).encode() in result
   case=re.search(rb'\[fault-bundle\] saved (/FAULTS/[0-9a-f]{32})',result);assert case
   case_paths[mode]=(case.group(1).decode(),vector)
   summary['checks'].append({'name':'guest_exception_'+mode,'vector':vector})
  cancel_start=len(g.output);send_bytes(g,b'diag /bin/fcases.elf spin\r');g.expect(b'FB12_SPIN',start=cancel_start,timeout=45)
  send_bytes(g,b'\x1b');g.expect(b'kind=killed',start=cancel_start,timeout=45);g.expect_supervisor(start=cancel_start,timeout=45)
  assert b'[fault-bundle] saved' not in bytes(g.output)[cancel_start:]
  summary['checks'].append({'name':'guest_cancel_no_false_fault_bundle'})
  result=command(g,'diag /bin/fault.elf',b'[fault-bundle] saved ',timeout=90)
  assert b'kind=faulted code=0 vector=14' in result
  match=re.search(rb'\[fault-bundle\] saved (/FAULTS/[0-9a-f]{32})',result);assert match,result[-1000:]
  path=match.group(1).decode();assert resources(g)==baseline
  summary['checks'].append({'name':'faulted_process_resources_reclaimed','baseline':baseline})
  command(g,'sync',b'sync=ok');(out/'first.serial.log').write_bytes(g.output);g.close();g=None
  for mode,(case_path,vector) in case_paths.items():
   case_dir=tmp/mode;case_dir.mkdir()
   for name in ('report.json','image.json','context.json','manifest.json'):transfer(disk,'export',case_path+'/'+name,case_dir/name)
   case_report,case_image=validate(case_dir);assert case_report['vector']==vector and case_report['address'] is None
   assert case_image['sha256']==hashlib.sha256(fixture_elf.read_bytes()).hexdigest()
   summary['checks'].append({'name':'guest_report_fields_'+mode,'vector':vector,'address':None})
  bundle=tmp/'bundle';bundle.mkdir()
  for name in ('report.json','image.json','context.json','manifest.json'):transfer(disk,'export',path+'/'+name,bundle/name)
  report,image=validate(bundle);captured=out/'bundle';captured.mkdir(exist_ok=True)
  for name in ('report.json','image.json','context.json','manifest.json'):(captured/name).write_bytes((bundle/name).read_bytes())
  assert image['sha256']==hashlib.sha256(run.read_bytes()).hexdigest();assert report['vector']==14
  binding=tmp/'binding.json';subprocess.run([sys.executable,str(ROOT/'scripts/fb2_bind_symbols.py'),str(run),str(symbols),str(binding)],check=True)
  (out/'binding.json').write_bytes(binding.read_bytes())
  resolved=symbolize(bundle,run,symbols,binding,'x86_64-elf-addr2line');assert 'fault_test.cpp:' in resolved['location'],resolved
  summary['checks'].append({'name':'guest_fault_bundle_and_bound_symbol','path':path,'location':resolved['location'],'run_sha256':image['sha256']})
  before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()}
  boot('reboot');command(g,'cat '+path+'/report.json',b'"outcome":"faulted"');(out/'reboot.serial.log').write_bytes(g.output);g.close();g=None
  for name in before:transfer(disk,'export',path+'/'+name,tmp/name);assert hashlib.sha256((tmp/name).read_bytes()).hexdigest()==before[name]
  summary['checks'].append({'name':'sync_reboot_exact_bytes','files':before})
  boot('no_entropy','qemu64,-rdrand');res=command(g,'diag /bin/fault.elf',b'[fault-bundle] not saved; result unknown',timeout=90);assert b'kind=faulted' in res
  summary['checks'].append({'name':'random_unavailable_preserves_fault'})
  command(g,'rm /bin/fault.elf',b'[files] removed')
  start=len(g.output);send_bytes(g,b'edit /bin/fault.elf\r');g.expect(b'| ',start=start,timeout=30)
  send_bytes(g,b'replacement is not the original ELF\r');g.expect(b'| ',start=start,timeout=30)
  send_bytes(g,b':wq\r');g.expect(b'[edit] saved',start=start,timeout=30);g.expect_supervisor(start=start,timeout=30)
  command(g,'sync',b'sync=ok');(out/'replacement.serial.log').write_bytes(g.output);g.close();g=None
  changed=tmp/'changed.elf';transfer(disk,'export','/bin/fault.elf',changed);assert hashlib.sha256(changed.read_bytes()).hexdigest()!=image['sha256']
  transfer(disk,'export',path+'/image.json',tmp/'image_after.json');assert hashlib.sha256((tmp/'image_after.json').read_bytes()).hexdigest()==before['image.json']
  summary['checks'].append({'name':'changed_path_does_not_rebind_original_report'})
  disk=tmp/'quota.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/fault.elf',run);transfer(disk,'mkdir','/FAULTS')
  for i in range(16):transfer(disk,'mkdir','/FAULTS/'+format(i,'032x'))
  sentinel=tmp/'sentinel';sentinel.write_bytes(b'user data is retained\n');transfer(disk,'import','/FAULTS/'+format(0,'032x')+'/keep.txt',sentinel)
  boot('quota');res=command(g,'diag /bin/fault.elf',b'[fault-bundle] not saved; result unknown',timeout=90);assert b'kind=faulted' in res
  (out/'quota.serial.log').write_bytes(g.output);g.close();g=None
  saved=tmp/'sentinel.out';transfer(disk,'export','/FAULTS/'+format(0,'032x')+'/keep.txt',saved);assert saved.read_bytes()==sentinel.read_bytes()
  summary['checks'].append({'name':'quota_refuses_without_deleting_user_file'})
  disk=tmp/'full.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/fault.elf',run);alter(disk,'full')
  boot('full');res=command(g,'diag /bin/fault.elf',b'[fault-bundle] not saved; result unknown',timeout=90);assert b'kind=faulted' in res
  (out/'full.serial.log').write_bytes(g.output);g.close();g=None
  summary['checks'].append({'name':'full_disk_preserves_fault'})
  disk=tmp/'io.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/fault.elf',run)
  preserved=tmp/'preserved';preserved.write_bytes(b'preexisting user data\n');transfer(disk,'import','/KEEP.TXT',preserved)
  original_command=boot_smoke.qemu_command
  def qemu(*args,**kwargs):
   cmd=original_command(*args,**kwargs)
   for i,v in enumerate(cmd):
    if v.startswith('file='+str(disk)+','):cmd[i]=v+',id=workdisk,node-name=workraw,werror=report,rerror=report'
   return cmd
  with patch.object(boot_smoke,'qemu_command',qemu):
   boot('ioerror')
  begin=len(g.output);send_bytes(g,b'diag /bin/fault.elf\r');g.expect(b'[fault] testing protected memory',start=begin,timeout=45)
  g.qmp('stop');nodes=g.qmp('query-named-block-nodes');node=next(n['node-name'] for n in nodes if n['drv']=='file' and n.get('file')==str(disk))
  g.qmp('blockdev-add',{'driver':'blkdebug','node-name':'fb12fault','image':node,'inject-error':[{'event':'write_aio','errno':5,'once':True}]})
  g.qmp('blockdev-reopen',{'options':[{'driver':'raw','node-name':'workraw','file':'fb12fault'}]});g.qmp('cont')
  g.expect(b'[fault-bundle] not saved; result unknown',start=begin,timeout=90);g.expect_supervisor(start=begin,timeout=30)
  assert b'[fault-bundle] saved ' not in bytes(g.output)[begin:];(out/'ioerror.serial.log').write_bytes(g.output);g.close();g=None
  kept=tmp/'preserved.out';transfer(disk,'export','/KEEP.TXT',kept);assert kept.read_bytes()==preserved.read_bytes()
  summary['checks'].append({'name':'real_write_error_no_false_success_preserves_other_file'})
  summary['status']='passed'
except Exception as error:summary['error']=str(error);raise
finally:
 if g:(out/'failed.serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
print('PASS FB1/FB2',len(summary['checks']))
