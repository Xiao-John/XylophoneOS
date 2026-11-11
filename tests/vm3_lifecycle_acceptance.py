#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify VM3 fork, rollback, cancellation and exec in a probe image."""
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root/'tests'),str(root/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command, resources
from make_work_disk import create_fat32
from work_disk import transfer
from toolchain import COMMON_FLAGS, X86_FLAGS, tool

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--system',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 system=a.system.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((system/'manifest.json').read_text());assert manifest['vm1_probe'] is True
 for name,digest in manifest['sources'].items(): assert sha(root/name)==digest,name
 for name,item in manifest['artifacts'].items(): assert sha(system/name)==item['sha256'],name
 sdk=system/'sdk';obj=out/'probe.o';binary=out/'probe.elf'
 subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(root/'tests/fixtures/vm3/lifecycle_probe.cpp'),'-o',str(obj)],check=True)
 subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(obj),str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),'-o',str(binary)],check=True)
 result={'status':'failed','build_id':manifest['build_id'],'image_sha256':sha(system/'xos-install.iso'),'probe_sha256':sha(binary),'checks':[]};guest=None
 try:
  with tempfile.TemporaryDirectory(prefix='xos_vm3_') as temp:
   disk=Path(temp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/vm3.elf',binary)
   guest=Guest(system/'xos-install.iso',str(out.relative_to(root/'build'))+'/guest',work_disk=disk,iso=True)
   result['qemu_command']=guest.command
   guest.expect(b'xos64> ',timeout=60);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=60)
   command(guest,'demo keep',b'demo: keep')
   for pid in (1,3,4):command(guest,f'kill {pid}',b'kill: accepted')
   pump(guest,.3);baseline=resources(guest);result['baseline']=baseline
   for i in range(2):
    start=len(guest.output);send_bytes(guest,b'exec-driver /bin/vm3.elf\r')
    guest.expect_any((b'kind=exited code=',b'kind=faulted',b'kind=killed'),start=start,timeout=900)
    guest.expect_supervisor(start=start,timeout=90)
    output=bytes(guest.output)[start:]
    assert b'kind=exited code=0' in output,output[-2000:]
    assert b'VM3_FORK_OOM_SWEEP_PASS' in output and b'VM3_FORK_PASS' in output and b'VM3_CHILD_PASS' in output and b'VM3_EXEC_PASS' in output and b'VM3_FAIL' not in output,output[-1500:]
    samples=[]
    for _ in range(5):
     sample=resources(guest);samples.append(sample)
     if sample==baseline: break
     pump(guest,.3)
    result.setdefault('resource_samples',[]).append(samples)
    assert samples[-1]==baseline,samples
    result['checks'].append('lifecycle_fork_oom_exec_'+str(i))
   start=len(guest.output);send_bytes(guest,b'exec-driver /bin/vm3.elf cancel\r')
   guest.expect(b'VM3_CANCEL_FORK_START',start=start,timeout=120)
   guest.expect(b'[vm3-fork] preparing',start=start,timeout=120)
   pump(guest,.4);send_bytes(guest,b'\x1b')
   guest.expect(b'kind=killed',start=start,timeout=120);guest.expect_supervisor(start=start,timeout=90)
   assert b'[vm3-fork] rolling_back' in bytes(guest.output)[start:]
   assert b'VM3_FAIL' not in bytes(guest.output)[start:]
   assert resources(guest)==baseline
   result['checks'].append('cancel_large_fork_and_reclaim')
   result['status']='passed'
 finally:
  if guest:(out/'guest.serial.log').write_bytes(guest.output);guest.close()
  (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS VM3 private lifecycle qualification')
if __name__=='__main__':main()
