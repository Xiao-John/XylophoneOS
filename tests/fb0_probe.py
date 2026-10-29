#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""FB0 file-instance and service-death probes, isolated test images only."""
import hashlib,json,re,subprocess,sys,tempfile
from unittest.mock import patch
import boot_smoke
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command
from toolchain import COMMON_FLAGS,X86_FLAGS,tool
out=ROOT/'build/fb0';out.mkdir(parents=True,exist_ok=True);sdk=ROOT/'build/sdk';src=ROOT/'tests/fixtures/fb0/file_probe.cpp'
manifest=json.loads((ROOT/'build/manifest.json').read_text())
for name,digest in manifest['sources'].items():
 if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise SystemExit('stale source: '+name)
for name,info in manifest['artifacts'].items():
 if hashlib.sha256((ROOT/'build'/name).read_bytes()).hexdigest()!=info['sha256']:raise SystemExit('artifact mismatch: '+name)
obj=out/'probe.o';elf=out/'probe.elf'
subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(src),'-o',str(obj)],check=True)
subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),'-Wl,--wrap=_ZN3xos4file6Client4openEPKcjRjS4_S4_',str(sdk/'crt0.o'),str(obj),'-Wl,--start-group',str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),'-Wl,--end-group','-o',str(elf)],check=True)
report={'status':'failed','checks':[],'not_run':['file_service_process_death','power_loss','kernel_panic','fault_snapshot','production_report_writer'],'build_id':manifest['build_id'],'fixture_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'sha_fixture_sha256':hashlib.sha256((src.parent/'sha256.hpp').read_bytes()).hexdigest(),'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest()};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_fb0_') as tmp:
  disk=Path(tmp)/'disk.img';sample=Path(tmp)/'sample';sample.write_bytes(bytes(range(256))*3)
  create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/probe.elf',elf);transfer(disk,'import','/bin/fault.elf',ROOT/'build/user_fault.image.elf');transfer(disk,'import','/PROBE.DAT',sample)
  base_command=boot_smoke.qemu_command
  def qemu(*args,**kwargs):
   cmd=base_command(*args,**kwargs)
   for i,v in enumerate(cmd):
    if v.startswith('file='+str(disk)+','):cmd[i]=v+',id=workdisk,node-name=workraw,werror=report,rerror=report'
   return cmd
  with patch.object(boot_smoke,'qemu_command',qemu):g=Guest(ROOT/'build/xos.img','fb0/guest',work_disk=disk)
  report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=30);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=30);command(g,'demo keep',b'demo: keep');
  for pid in (1,3,4):command(g,f'kill {pid}',b'kill: accepted')
  pump(g,.5)
  result=command(g,'exec-file /bin/probe.elf',b'FB0_PINNED_OK',timeout=30)
  match=re.search(rb'FB0_BYTES=([0-9a-f]+)',result);assert match
  observed=bytes.fromhex(match.group(1).decode());assert observed==sample.read_bytes()
  replace=re.search(rb'FB0_REPLACE=(-?\d+)',result);assert replace and int(replace.group(1))<0
  assert b'kind=exited code=0' in result
  report['checks'].append({'name':'same_handle_read_replace_and_reread','sha256':hashlib.sha256(observed).hexdigest(),'replace_status':int(replace.group(1))})
  hashed=command(g,'exec-file /bin/probe.elf hash',b'FB0_ELF_SHA256=',timeout=45)
  digest=re.search(rb'FB0_ELF_SHA256=([0-9a-f]{64})',hashed);assert digest and digest.group(1).decode()==hashlib.sha256(elf.read_bytes()).hexdigest()
  assert b'kind=exited code=0' in hashed
  report['checks'].append({'name':'guest_elf_sha256_same_read_handle','sha256':digest.group(1).decode()})
  loader=command(g,'exec-driver /bin/probe.elf loader',b'FB0_LOADER_WAIT_OK',timeout=60)
  loader_hash=re.search(rb'FB0_LOADER_SHA256=([0-9a-f]{64})',loader)
  assert loader_hash and loader_hash.group(1).decode()==hashlib.sha256((ROOT/'build/user_fault.image.elf').read_bytes()).hexdigest()
  assert b'FB0_INVALID_WAIT=-2' in loader and b'FB0_WAIT_RESULT=0' in loader and b'FB0_WAIT_VECTOR=14' in loader and b'FB0_WAIT_ADDRESS=1048576' in loader and b'FB0_WAIT_AGAIN=-1' in loader and b'kind=exited code=0' in loader
  report['checks'].append({'name':'loader_open_instance_sha256_and_wait_single_consumption','sha256':loader_hash.group(1).decode(),'output':loader.decode(errors='replace')})
  fault=command(g,'exec fault',b'kind=faulted code=0',timeout=30)
  assert b'vector=14' in fault and b'address=1048576' in fault and b'event=fault' in fault and b'rip=' in fault
  normal=command(g,'exec demo',b'kind=exited code=42',timeout=30)
  report['checks'].append({'name':'fault_status_then_normal_program','fault_output':fault.decode(errors='replace'),'normal_exit':42})
  ps=command(g,'ps',b'files');(out/'ps.txt').write_bytes(ps)
  report['service_discovery']=ps.decode(errors='replace')
  begin=len(g.output);send_bytes(g,b'spawn-file /bin/probe.elf degraded\r');g.expect(b'FB0_DEATH_READY',start=begin,timeout=30);g.expect_supervisor(start=begin)
  g.qmp('stop');nodes=g.qmp('query-named-block-nodes')
  node=next(n['node-name'] for n in nodes if n['drv']=='file' and n.get('file')==str(disk))
  g.qmp('blockdev-add',{'driver':'blkdebug','node-name':'fb0fault','image':node,'inject-error':[{'event':'write_aio','errno':5,'once':True}]})
  g.qmp('blockdev-reopen',{'options':[{'driver':'raw','node-name':'workraw','file':'fb0fault'}]});g.qmp('cont')
  begin_save=len(g.output);send_bytes(g,b'edit /NEW.TXT\r');g.expect(b'| ',start=begin_save,timeout=30);send_bytes(g,b'fb0 write\r');g.expect(b'| ',start=begin_save,timeout=30);send_bytes(g,b':wq\r');g.expect(b'[files] save error=-7',start=begin_save,timeout=30);g.expect(b'| ',start=begin_save,timeout=30);response=bytes(g.output)[begin_save:];send_bytes(g,b':q!\r');g.expect_supervisor(start=begin_save,timeout=30)
  g.expect(b'FB0_DEATH_PING=-7\n',start=begin,timeout=45)
  match=re.search(rb'FB0_DEATH_PING=(-?\d+)',bytes(g.output)[begin:]);assert match
  assert b'[files] save error=-7' in response and int(match.group(1)) == -7
  report['checks'].append({'name':'blkdebug_write_error','save_output':response.decode(errors='replace'),'ping_status':int(match.group(1))})
  report['status']='passed'
except Exception as error:report['error']=str(error);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS FB0',len(report['checks']))
