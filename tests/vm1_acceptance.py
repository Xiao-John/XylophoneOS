#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the private VM1 probe without publishing sys_vm."""
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
 p=argparse.ArgumentParser();p.add_argument('--system',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--expect-disabled',action='store_true');a=p.parse_args()
 system=a.system.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((system/'manifest.json').read_text());assert manifest['vm1_probe'] is (not a.expect_disabled)
 for name,digest in manifest['sources'].items(): assert sha(root/name)==digest,name
 for name,item in manifest['artifacts'].items(): assert sha(system/name)==item['sha256'],name
 sdk=system/'sdk';obj=out/'probe.o';binary=out/'probe.elf'
 subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(root/('tests/fixtures/vm1/no_public.cpp' if a.expect_disabled else 'tests/fixtures/vm1/guest_probe.cpp')),'-o',str(obj)],check=True)
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
   for i in range(2):
    output=command(guest,'exec-file /bin/vm1.elf',b'kind=exited code=0',timeout=90)
    assert (b'VM1_PUBLIC_PASS' if a.expect_disabled else b'VM1_GUEST_PASS') in output and b'VM1_FAIL' not in output,output[-1500:]
    assert resources(guest)==baseline
    result['checks'].append(('public_vm_private_diagnostics_disabled_' if a.expect_disabled else 'guest_sparse_4t_fragment_split_and_reuse_')+str(i))
   if not a.expect_disabled:
    fault=command(guest,'exec-file /bin/vm1.elf fault',b'kind=faulted',timeout=90)
    assert b'VM1_RESERVED_READ' in fault and b'vector=14' in fault, fault[-1500:]
    assert resources(guest)==baseline
    result['checks'].append('reserved_none_causes_page_fault_and_reclaims')
   result['status']='passed'
 finally:
  if guest:(out/'guest.serial.log').write_bytes(guest.output);guest.close()
  (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS VM1 private guest qualification')
if __name__=='__main__':main()
