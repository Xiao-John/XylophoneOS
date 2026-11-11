#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify private VM2 page operations using actual user faults."""
import argparse, hashlib, json, re, subprocess, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/'tests'),str(root/'scripts')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command, resources
from make_work_disk import create_fat32
from work_disk import transfer
from toolchain import COMMON_FLAGS, X86_FLAGS, tool

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--system',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--expect-disabled',action='store_true');p.add_argument('--sweep',action='store_true');p.add_argument('--icount',action='store_true');a=p.parse_args()
 if a.expect_disabled:
  p.error('page fault injection requires the probe image; use vm1_acceptance.py --expect-disabled for the public image')
 if a.icount:
  assert a.sweep, '--icount is intended only for the allocation sweep'
  qemu_command=boot_smoke.qemu_command
  def accelerated_command(*args,**kwargs):
   return qemu_command(*args,**kwargs)+['-icount','shift=7,align=off,sleep=off']
  boot_smoke.qemu_command=accelerated_command
 system=a.system.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((system/'manifest.json').read_text());assert manifest['vm1_probe'] is (not a.expect_disabled)
 for name,digest in manifest['sources'].items(): assert sha(root/name)==digest,name
 for name,item in manifest['artifacts'].items(): assert sha(system/name)==item['sha256'],name
 sdk=system/'sdk';obj=out/'probe.o';binary=out/'probe.elf'
 subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(root/'tests/fixtures/vm2/pages_probe.cpp'),'-o',str(obj)],check=True)
 subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(obj),str(sdk/'lib/libxos.a'),'-o',str(binary)],check=True)
 result={'status':'failed','build_id':manifest['build_id'],'image_sha256':sha(system/'xos-install.iso'),'probe_sha256':sha(binary),'checks':[]};guest=None
 try:
  with tempfile.TemporaryDirectory(prefix='xos_vm1_') as temp:
   disk=Path(temp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/vm1.elf',binary)
   guest=Guest(system/'xos-install.iso',str(out.relative_to(root/'build'))+'/guest',work_disk=disk,iso=True)
   result['qemu_command']=guest.command
   guest.expect(b'xos64> ',timeout=60);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=60)
   command(guest,'demo keep',b'demo: keep')
   for pid in (1,3,4):command(guest,f'kill {pid}',b'kill: accepted')
   pump(guest,.3);baseline=resources(guest);result['baseline']=baseline
   if a.sweep:
    start=len(guest.output); position=start
    send_bytes(guest,b'exec-file /bin/vm1.elf sweep\r')
    while True:
     marker=guest.expect_any((b'VM2_SWEEP_THROUGH=',b'VM2_SWEEP_PASS',b'VM2_SWEEP_FAILED_AT=',b'VM2_PAGES_FAIL',b'kind=faulted'),start=position,timeout=14400)
     position=guest.output.find(marker,position)+len(marker)
     if marker==b'VM2_SWEEP_THROUGH=':
      guest.expect(b'\n',start=position,timeout=30)
      end=guest.output.index(b'\n',position)
      print('VM2 sweep through '+guest.output[position:end].decode().strip(),flush=True)
      position=end+1
      continue
     assert marker==b'VM2_SWEEP_PASS',bytes(guest.output)[start:][-1500:]
     break
    guest.expect(b'kind=exited code=0',start=start,timeout=120)
    guest.expect_supervisor(start=start,timeout=120)
    assert resources(guest)==baseline
    result['checks'].append('all_4096_allocation_failure_positions_and_content_rollback')
   else:
    for i in range(1):
     output=command(guest,'exec-file /bin/vm1.elf',b'kind=exited code=0',timeout=90)
     assert b'VM2_PAGES_PASS' in output and b'VM2_CROSS_IN_OK' in output and b'VM2_PAGES_FAIL' not in output,output[-1500:]
     assert resources(guest)==baseline
     result['checks'].append(('guest_disabled_' if a.expect_disabled else 'guest_sparse_4t_fragment_split_and_reuse_')+str(i))
    for mode, marker in [('readwriteexec','RW_EXEC'),('readwrite','R_WRITE'),('rxwrite','RX_WRITE'),('noneread','NONE_READ'),('nonewrite','NONE_WRITE'),('noneexec','NONE_EXEC')]:
     fault=command(guest,'exec-file /bin/vm1.elf '+mode,b'kind=faulted',timeout=120)
     assert ('VM2_FAULT_'+marker).encode() in fault and b'vector=14' in fault, fault[-1500:]
     assert resources(guest)==baseline
     result['checks'].append('user_fault_'+mode)
    for phase in ('staging','publishing'):
     start=len(guest.output)
     spawned=command(guest,'spawn-file /bin/vm1.elf kill',b'[loader] started pid=',timeout=90)
     match=re.search(rb'\[loader\] started pid=(\d+)',spawned);assert match,spawned[-1000:]
     pid=int(match.group(1))
     guest.expect(('[vm2-pages] '+phase).encode(),start=start,timeout=90)
     command(guest,'kill '+str(pid),b'kill: accepted',timeout=90)
     command(guest,'wait '+str(pid),b'kind=killed',timeout=120)
     assert resources(guest)==baseline
     result['checks'].append('kill_during_'+phase+'_reclaims')
   result['status']='passed'
 finally:
  if guest:(out/'guest.serial.log').write_bytes(guest.output);guest.close()
  (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS VM2 page guest qualification')
if __name__=='__main__':main()
