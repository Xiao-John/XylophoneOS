#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise bounded VM continuation scheduling and cancellation in QEMU."""
import argparse, hashlib, json, re, subprocess, sys, tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'tests'),str(root/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command, resources
from make_work_disk import create_fat32
from work_disk import transfer
from toolchain import COMMON_FLAGS, X86_FLAGS, tool

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--system',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((system/'manifest.json').read_text());assert manifest['vm1_probe'] is True
    for name,digest in manifest['sources'].items(): assert sha(root/name)==digest,name
    for name,item in manifest['artifacts'].items(): assert sha(system/name)==item['sha256'],name
    sdk=system/'sdk';obj=out/'probe.o';binary=out/'probe.elf'
    subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-I',str(sdk/'include'),'-c',str(root/'tests/fixtures/vm2/continuation_probe.cpp'),'-o',str(obj)],check=True)
    subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(obj),str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),'-o',str(binary)],check=True)
    thread_obj=out/'thread_probe.o';thread_binary=out/'thread_probe.elf'
    subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-ftls-model=local-exec','-I',str(root/'src/user/include'),'-I',str(sdk/'include'),'-c',str(root/'tests/fixtures/vm2/continuation_threads.cpp'),'-o',str(thread_obj)],check=True)
    subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(thread_obj),str(system/'threading_core/libxos_thread_core.a'),str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),'-o',str(thread_binary)],check=True)
    pin_obj=out/'wait_pin_probe.o';pin_binary=out/'wait_pin_probe.elf'
    subprocess.run([tool('g++'),*COMMON_FLAGS,*X86_FLAGS,'-ftls-model=local-exec','-I',str(root/'src/user/include'),'-I',str(sdk/'include'),'-c',str(root/'tests/fixtures/vm2/wait_pin_probe.cpp'),'-o',str(pin_obj)],check=True)
    subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(pin_obj),str(system/'threading_core/libxos_thread_core.a'),str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),'-o',str(pin_binary)],check=True)
    report={'status':'failed','build_id':manifest['build_id'],'image_sha256':sha(system/'xos-install.iso'),'probe_sha256':sha(binary),'thread_probe_sha256':sha(thread_binary),'pin_probe_sha256':sha(pin_binary),'checks':[]};guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_vm2_') as tmp:
            disk=Path(tmp)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/vm2.elf',binary)
            transfer(disk,'import','/bin/threading.elf',system/'user_threading_core_probe.image.elf')
            transfer(disk,'import','/bin/vm2threads.elf',thread_binary)
            transfer(disk,'import','/bin/vm2pin.elf',pin_binary)
            transfer(disk,'import','/bin/slow.elf',system/'user_slow.image.elf')
            transfer(disk,'import','/bin/spin.elf',system/'user_spin.image.elf')
            guest=Guest(system/'xos-install.iso',str(out.relative_to(root/'build'))+'/guest',work_disk=disk,iso=True)
            report['qemu_command']=guest.command
            guest.expect(b'xos64> ',timeout=60);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=60)
            command(guest,'demo keep',b'demo: keep')
            for pid in (1,3,4):command(guest,f'kill {pid}',b'kill: accepted')
            pump(guest,.2);baseline=resources(guest);report['baseline']=baseline
            thread=command(guest,'exec-file /bin/threading.elf core',b'kind=exited code=0',timeout=120)
            assert b'pins=ok' in thread and resources(guest)==baseline
            report['checks'].append('thread_wait_word_pin_and_release')
            pin=command(guest,'exec-driver /bin/vm2pin.elf',b'kind=exited code=0',timeout=120)
            assert b'VM2_READY_CROSS_PAGE_PIN_PASS' in pin and resources(guest)==baseline
            report['checks'].append('ready_process_wait_pin_covers_both_pages_until_copyout')
            peers=command(guest,'exec-file /bin/vm2threads.elf',b'kind=exited code=0',timeout=120)
            assert b'VM2_PEER_FROZEN_PASS' in peers and resources(guest)==baseline
            report['checks'].append('same_process_peer_frozen_during_transaction')
            result=command(guest,'exec-file /bin/vm2.elf',b'kind=exited code=0',timeout=120)
            assert b'VM2_PROBE_COMPLETE' in result and b'[vm2-probe] publishing' in result
            assert resources(guest)==baseline
            report['checks'].append('bounded_completion_monotonic_clock_and_reclamation')
            failed=command(guest,'exec-file /bin/vm2.elf fail',b'kind=exited code=0',timeout=120)
            assert b'VM2_PROBE_COMPLETE' in failed and b'[vm2-probe] rolling_back' in failed
            assert resources(guest)==baseline
            report['checks'].append('injected_staging_failure_rolls_back')
            for phase in ('preparing','publishing'):
                start=len(guest.output)
                spawned=command(guest,'spawn-file /bin/vm2.elf',b'[loader] started pid=',timeout=90)
                match=re.search(rb'\[loader\] started pid=(\d+)',spawned);assert match,spawned[-1000:]
                pid=int(match.group(1));guest.expect(('[vm2-probe] '+phase).encode(),start=start,timeout=90)
                command(guest,'kill '+str(pid),b'kill: accepted',timeout=90)
                result=command(guest,'wait '+str(pid),b'kind=killed',timeout=120)
                combined=bytes(guest.output)[start:]
                if phase=='preparing':assert b'[vm2-probe] rolling_back' in combined
                assert b'VM2_PROBE_COMPLETE' not in combined
                assert resources(guest)==baseline
                report['checks'].append('cancel_'+phase+'_other_process_runs_and_reclaims')
            start=len(guest.output)
            send_bytes(guest,b'exec-driver /bin/vm2.elf child\r')
            guest.expect(b'[vm2-probe] preparing',start=start,timeout=90)
            output=bytes(guest.output)[start:]
            child=re.search(rb'VM2_CHILD_PID=(\d+)',output);assert child,output[-1500:]
            send_bytes(guest,b'\x1b')
            guest.expect(b'kind=killed',start=start,timeout=120);guest.expect_supervisor(start=start,timeout=90)
            output=bytes(guest.output)[start:]
            reclaimed=b'[task] event=reclaimed pid='+child.group(1)+b' '
            assert reclaimed in output and output.index(reclaimed)<output.index(b'[vm2-probe] rolling_back'),output[-2000:]
            assert resources(guest)==baseline
            report['checks'].append('parent_cancel_propagates_to_child_before_rollback')
            command(guest,'kill 2',b'kill: accepted');pump(guest,.2)
            idle_baseline=resources(guest)
            idle=command(guest,'exec-file /bin/vm2.elf',b'kind=exited code=0',timeout=120)
            assert b'VM2_PROBE_COMPLETE' in idle and resources(guest)==idle_baseline
            report['checks'].append('no_other_runnable_process_clock_and_reclamation')
            report['status']='passed'
    finally:
        if guest:(out/'guest.serial.log').write_bytes(guest.output);guest.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS VM2 foundation guest qualification')
if __name__=='__main__':main()
