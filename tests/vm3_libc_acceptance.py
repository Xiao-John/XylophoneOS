#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the VM3 libc subset under xsh and an optional matching dash."""
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'tests'),str(root/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command, resources
from make_work_disk import create_fat32
from work_disk import transfer
from toolchain import X86_FLAGS, tool

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--system',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--dash',type=Path);a=p.parse_args()
 system=a.system.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((system/'manifest.json').read_text())
 for name,digest in manifest['sources'].items():assert sha(root/name)==digest,name
 for name,item in manifest['artifacts'].items():assert sha(system/name)==item['sha256'],name
 sdk=system/'sdk';obj=out/'probe.o';binary=out/'probe.elf'
 subprocess.run([tool('gcc'),'-std=c11','-O2','-ffreestanding','-fno-pie','-fno-stack-protector',*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(root/'tests/fixtures/vm3/libc_probe.c'),'-o',str(obj)],check=True)
 subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0_posix.o'),str(obj),'-Wl,--start-group',str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),str(sdk/'lib/libc.a'),str(sdk/'lib/libm.a'),'-lgcc','-Wl,--end-group','-o',str(binary)],check=True)
 report={'status':'failed','build_id':manifest['build_id'],'image_sha256':sha(system/'xos-install.iso'),'elf_sha256':sha(binary),'checks':[]};guest=None
 try:
  with tempfile.TemporaryDirectory(prefix='xos_vm3_libc_') as tmp:
   disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/vm3.elf',binary)
   if a.dash:transfer(disk,'import','/bin/dash.elf',a.dash.resolve());report['dash_sha256']=sha(a.dash.resolve())
   guest=Guest(system/'xos-install.iso',str(out.relative_to(root/'build'))+'/guest',work_disk=disk,iso=True);report['qemu_command']=guest.command
   guest.expect(b'xos64> ',timeout=60);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=60)
   command(guest,'demo keep',b'demo: keep')
   for pid in (1,3,4):command(guest,'kill '+str(pid),b'kill: accepted')
   pump(guest,.3);baseline=resources(guest);report['baseline']=baseline
   runs=[('xsh','exec-driver /bin/vm3.elf')]*2
   if a.dash:runs.append(('dash',"exec-driver /bin/dash.elf -c /bin/vm3.elf"))
   for name,cmd in runs:
    output=command(guest,cmd,b'kind=exited code=0',timeout=900)
    assert b'VM3_LIBC_PASS' in output,output[-2000:]
    samples=[]
    for _ in range(5):
     samples.append(resources(guest))
     if samples[-1]==baseline:break
     pump(guest,.3)
    assert samples[-1]==baseline,samples
    report['checks'].append(name+'_libc_fork_mapping')
   report['status']='passed'
 finally:
  if guest:(out/'guest.serial.log').write_bytes(guest.output);guest.close()
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print('PASS VM3 libc qualification')
if __name__=='__main__':main()
