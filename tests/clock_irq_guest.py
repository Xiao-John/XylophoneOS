# SPDX-License-Identifier: Apache-2.0
"""Test-only kernel ownership controls plus real guest clock/wait/RTC syscalls."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes
from process_smoke import command,resources
from work_disk import transfer
from toolchain import COMMON_FLAGS,X86_FLAGS,tool
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--system',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);system=a.system.resolve();sdk=system/'sdk';image=system/'xos-install.iso'
    manifest=json.loads((system/'manifest.json').read_text())
    assert manifest['clock_irq_probe'] is True
    assert sha(image)==manifest['artifacts']['xos-install.iso']['sha256']
    commands=[];g=None
    report={'status':'FAILED','build_id':manifest['build_id'],'image_sha256':sha(image),'boot_format':'ISO','checks':[],'commands':commands}
    try:
        source=ROOT/'tests/fixtures/clock_irq/clock_user.cpp';obj=out/'clock.o';elf=out/'clock.elf'
        env=os.environ.copy();env['COMPILER_PATH']=str(system/'target_tools')
        for cmd in [[tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I'+str(ROOT/'src/user/include'),'-I'+str(ROOT/'src/shared/include'),'-I'+str(sdk/'include'),'-c',str(source),'-o',str(obj)],
                    [tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(obj),str(sdk/'lib/libxos.a'),'-o',str(elf)]]:
            commands.append(cmd)
            with (out/'compile.log').open('ab') as log:subprocess.run(cmd,check=True,env=env,stdout=log,stderr=subprocess.STDOUT)
        report.update(elf_sha256=sha(elf),source_sha256=sha(source),sdk_manifest_sha256=sha(sdk/'manifest.json'))
        disk=out/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/clock',elf);report['disk_before_sha256']=sha(disk)
        report['host_wall_before_ns']=time.time_ns();g=Guest(image,'clock_irq/'+out.name,work_disk=disk,iso=True);report['qemu_command']=g.command
        g.expect(b'xos64> ',timeout=45);start=len(g.output);send_bytes(g,b'irq-audit\r');g.expect(b'irq-audit pass',start=start,timeout=20);g.expect(b'xos64> ',start=start)
        text=bytes(g.output[start:]);assert b' FAIL' not in text
        match=re.search(rb'\[irq-audit\] ticks=(\d+) ns=(\d+)',text);assert match;boot_ticks=int(match[1]);assert int(match[2])==boot_ticks*10000000
        report['boot_ticks']=boot_ticks;report['checks'].append('test_only_kernel_owner_EOI_mask_pre_run_controls')
        start=len(g.output);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,start=start,timeout=45)
        command(g,'demo quiet',b'demo tasks');baseline=resources(g);report['resources_before']=baseline
        for index in range(2):
            output=command(g,'exec-file /bin/clock',b'kind=exited code=0',timeout=45)
            match=re.search(rb'CLOCK_USER_OK:first=(\d+) last=(\d+) wall=(\d+)',output);assert match,output
            first,last,wall=map(int,match.groups());assert last>first>=boot_ticks
            report['host_wall_after_ns']=time.time_ns();assert report['host_wall_before_ns']-2000000000<=wall<=report['host_wall_after_ns']+2000000000
            assert resources(g)==baseline
            report['checks'].append({'clock_syscalls_wait_RTC_run':index,'first':first,'last':last,'RTC_epoch_ns':wall})
        report['resources_after']=resources(g);report['disk_after_sha256']=sha(disk);report['status']='PASSED'
    except Exception as error:report['error']=repr(error)
    finally:
        if g:
            g.close()
            for kind in ['serial','qemu']:shutil.copyfile(ROOT/f'build/{g.name}_{kind}.log',out/(kind+'.log'))
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));raise SystemExit(report['status']!='PASSED')
if __name__=='__main__':main()
