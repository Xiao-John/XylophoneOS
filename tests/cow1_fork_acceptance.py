#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise an explicitly opted-in COW1 fork on the isolated probe image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from toolchain import X86_FLAGS, tool
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    system=args.system.resolve(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((system/'manifest.json').read_text())
    assert manifest['vm1_probe'] and manifest['cow1_probe']
    for path,digest in manifest['sources'].items(): assert sha(ROOT/path)==digest, path
    for path,item in manifest['artifacts'].items(): assert sha(system/path)==item['sha256'], path
    sdk=system/'sdk'; obj=out/'probe.o'; binary=out/'probe.elf'
    subprocess.run([tool('gcc'),'-std=c11','-O2','-ffreestanding','-fno-pie','-fno-stack-protector',
                    *X86_FLAGS,'-I',str(sdk/'include'),'-c',str(ROOT/'tests/fixtures/cow1/fork_probe.c'),'-o',str(obj)],check=True)
    subprocess.run([tool('g++'),*X86_FLAGS,'-nostdlib','-static','-no-pie',
                    '-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096',
                    '-T',str(sdk/'user.ld'),str(sdk/'crt0_posix.o'),str(obj),'-Wl,--start-group',
                    str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libxos.a'),str(sdk/'lib/libc.a'),
                    str(sdk/'lib/libm.a'),'-lgcc','-Wl,--end-group','-o',str(binary)],check=True)
    report={'status':'failed','build_id':manifest['build_id'],'image_sha256':sha(system/'xos-install.iso'),
            'elf_sha256':sha(binary),'checks':[]}; guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_cow1_') as temp:
            disk=Path(temp)/'work.img'; create_fat32(disk,512); transfer(disk,'mkdir','/bin')
            transfer(disk,'import','/bin/cow1.elf',binary)
            guest=Guest(system/'xos-install.iso',str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk,iso=True)
            report['qemu_command']=guest.command
            guest.expect(b'xos64> ',timeout=60); send_bytes(guest,b'run\r'); guest.expect_supervisor(trace=True,timeout=60)
            command(guest,'demo quiet',b'demo tasks'); pump(guest,.2)
            baseline=resources(guest); report['baseline']=baseline
            for index in range(2):
                output=command(guest,'exec-driver /bin/cow1.elf',b'kind=exited code=',timeout=180)
                assert b'COW1_FORK_PASS' in output and b'COW1_FORK_OOM_SWEEP_PASS' in output and \
                       b'COW1_SHARED_PAGES ' in output and b'COW1_FAULT_OOM_PASS' in output and \
                       b'[cow1-probe] fault=cow_oom' in output and b'COW1_READONLY_FAULT_PASS' in output and \
                       b'COW1_ABORT_AFTER_PARENT_WRITE_PASS' in output and \
                       b'COW1_FILES_ACK_FAILURE_PASS' in output and \
                       b'[cow1-probe] fork_files_ack=injected_failure' in output and \
                       b'COW1_RETAIN_FAILURE_PASS' in output and b'COW1_RETAIN_SWEEP count=' in output and \
                       b'COW1_TLS_HEAP_PASS' in output and \
                       b'COW1_EXEC_IMAGE_PASS' in output and b'COW1_EXEC_PARENT_PASS' in output and \
                       b'COW1_CROSS_PAGE_STORE_PASS' in output and \
                       b'COW1_EXECUTION_PERMISSIONS_PASS' in output and \
                       b'kind=exited code=0' in output,output[-4000:]
                assert resources(guest)==baseline
                report['checks'].append('three_generation_private_fork_'+str(index))
            for phase,marker in [('preparing',b'[vm3-fork] preparing'),('publishing',b'[cow1-probe] publishing')]:
                start=len(guest.output)
                send_bytes(guest,b'exec-driver /bin/cow1.elf cancel\r')
                guest.expect(b'COW1_CANCEL_START',start=start,timeout=120)
                guest.expect(marker,start=start,timeout=120)
                send_bytes(guest,b'\x1b')
                guest.expect(b'kind=killed',start=start,timeout=120)
                guest.expect_supervisor(start=start,timeout=120)
                if phase=='preparing': assert b'[vm3-fork] rolling_back' in bytes(guest.output)[start:]
                assert resources(guest)==baseline
                report['checks'].append('cancel_'+phase+'_reclaims_resources')
            report['status']='passed'
    finally:
        if guest:
            (out/'guest.serial.log').write_bytes(guest.output); guest.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS isolated COW1 fork guest')


if __name__=='__main__': main()
