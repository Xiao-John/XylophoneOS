# SPDX-License-Identifier: Apache-2.0
"""P2-1 real guest admission barrier and file write lease; no package mutation yet."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes,pump
from xypm_image import Disk
from xypm_format import canonical,require,sha_file


def build_probe(sdk,output):
    compiler=shutil.which('x86_64-elf-gcc')
    libgcc=subprocess.check_output([compiler,'-print-libgcc-file-name'],text=True).strip()
    subprocess.run([compiler,'-O2','-mno-red-zone','-fno-pie','-fno-pic','-fno-stack-protector',
        '-fno-exceptions','-fno-rtti','-fno-threadsafe-statics','-fno-use-cxa-atexit',
        '-idirafter',str(sdk/'include'),'-nostdlib','-static','-no-pie',
        '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
        '-T',str(sdk/'user.ld'),str(sdk/'crt0.o'),str(ROOT/'tests/fixtures/package_p2/maintenance_probe.cpp'),
        '-Wl,--start-group',str(sdk/'lib/libxos.a'),libgcc,'-Wl,--end-group','-o',str(output)],check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',type=Path,default=ROOT/'build/package_p2_system')
    parser.add_argument('--output',type=Path,default=ROOT/'build/package_p2')
    args=parser.parse_args();system=args.system.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((system/'manifest.json').read_text())
    image=system/'xos.img';require(sha_file(image)==manifest['artifacts']['xos.img']['sha256'],'system image mismatch')
    probe=out/'maintenance_probe.elf';build_probe(system/'sdk',probe)
    report={'status':'failed','system_build_id':manifest['build_id'],'image_sha256':sha_file(image),
        'probe_sha256':sha_file(probe),'checks':[],
        'not_run':['guest_package_install_upgrade_remove','multi_file_journal_recovery','power_loss','old_stress','P3']}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p2_') as folder:
            folder=Path(folder);disk=folder/'work.img';create_fat32(disk,512)
            with Disk(disk,folder) as backend:
                backend.command('mkdir','/out');backend.command('import','/out/p2_probe',probe)
            boot=folder/'boot.img';shutil.copyfile(image,boot)
            guest=Guest(boot,'package_p2',work_disk=disk)
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
            baseline=resources(guest);report['baseline']=baseline
            def command(line,expected,stable=True):
                start=len(guest.output);send_bytes(guest,line.encode()+b'\r')
                guest.expect(expected,start=start,timeout=45);guest.expect_supervisor(start=start,timeout=45)
                data=bytes(guest.output)[start:]
                require(b'P2_PROBE_FAIL=' not in data,'probe failed: '+repr(data))
                if stable:require(resources(guest)==baseline,'resources drift: '+line)
                return data
            command('exec-file /out/p2_probe normal',b'P2_NORMAL denied_controls writes_ok')
            report['checks'].append('ordinary_controls_denied_and_normal_writes_allowed')
            command('maint-run /out/missing',b'session closed')
            command('maint-status',b'owner=0 worker=0 error=0')
            report['checks'].append('missing_program_releases_empty_session')
            data=command('spawn-file /out/p2_probe background',b'P2_BACKGROUND',False)
            pid=int(re.findall(rb'started pid=(\d+)',data)[-1])
            command('maint-run /out/p2_probe ok',b'busy or denied error=-11',False)
            command('kill '+str(pid),b'kill: accepted',False);command('wait '+str(pid),b'kind=killed code=-9')
            report['checks'].append('live_ordinary_process_blocks_maintenance')
            data=command('maint-run /out/p2_probe ok',b'maintenance: completed')
            command('maint-status',b'owner=0 worker=0 error=0')
            report['checks'].append('exclusive_worker_write_lease_and_no_spawn')
            require(b'P2_C_STAGE isolated_abi new_paths_guarded' in data,'C-stage guard probe missing')
            report['checks'].append('c1_c3_abi_and_new_creation_paths_guarded')
            for mode in ('fail','fault','spin'):
                if mode=='spin':
                    start=len(guest.output);send_bytes(guest,b'maint-run /out/p2_probe spin\r')
                    guest.expect(b'P2_WORKER lease_ok spawn_denied',start=start,timeout=40)
                    send_bytes(guest,b'\x1b');guest.expect(b'maintenance: retained',start=start,timeout=40)
                    guest.expect_supervisor(start=start,timeout=40)
                    require(resources(guest)==baseline,'resources drift after Escape')
                else:command('maint-run /out/p2_probe '+mode,b'maintenance: retained')
                command('exec-file /out/p2_probe normal',b'error=-11')
                command('mkdir /out/blocked_'+mode,b'error=-5')
                command('cat /out/p2_worker.txt',b'worker')
                command('maint-run /out/p2_probe ok',b'busy or denied error=-11')
                command('maint-recover /out/not_present',b'maintenance: retained')
                command('maint-recover /out/p2_probe recover',b'maintenance: completed')
                command('maint-status',b'owner=0 worker=0 error=0')
                command('exec-file /out/p2_probe normal',b'P2_NORMAL denied_controls writes_ok')
                report['checks'].append(mode+'_retains_barrier_recovery_restores_admission')
            command('sync',b'[files] sync=ok')
            guest.close();(out/'serial.log').write_bytes(guest.output);guest=None
            with Disk(disk,folder,True) as backend:
                require(backend.export('/out/p2_worker.txt').read_bytes()==b'recovered','recovery payload missing')
                require(backend.info('/out/p2_without_lease.txt') is None,'write without lease escaped')
                for mode in ('fail','fault','spin'):require(backend.info('/out/blocked_'+mode) is None,'blocked write escaped')
            report['checks'].append('persisted_effects_and_blocked_paths_verified')
            report['final_resources']=baseline;report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-6000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed_serial.log').write_bytes(guest.output)
        (out/'maintenance_report.json').write_bytes(canonical(report))
    print(canonical(report).decode())
if __name__=='__main__':main()
