# SPDX-License-Identifier: Apache-2.0
"""One real XOS run: two inherited pipe writers, 512-byte atomic records."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command,resources
from task_smoke import send_bytes,pump
from work_disk import transfer


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',type=Path,default=ROOT/'build')
    parser.add_argument('--report',type=Path,default=ROOT/'build/pipe_atomic_report.json')
    parser.add_argument('--artifacts',type=Path,default=ROOT/'build/pipe_atomic_evidence')
    args=parser.parse_args();args.system=args.system.resolve()
    run_id=uuid.uuid4().hex;args.artifacts=args.artifacts.resolve()/run_id
    args.artifacts.mkdir(parents=True,exist_ok=False)
    report={'status':'failed','run_id':run_id,'scope':'one directed two-process inherited-pipe atomic-write run',
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'sources':{},'tools':{},'build_commands':[],'checks':[],
            'expected':{'writers':2,'records_each':64,'write_bytes':512,'read_chunk':257,'bytes':65536,'exit_code':0},
            'not_run':['SMP','long_randomized_stress']}
    guest=None
    try:
        sdk=args.system/'sdk';manifest_path=args.system/'manifest.json'
        manifest=json.loads(manifest_path.read_text());sdk_manifest=json.loads((sdk/'manifest.json').read_text())
        image=args.system/'xos.img'
        report.update(system_build_id=manifest['build_id'],system_manifest_sha256=sha(manifest_path),
                      xos_sha256=sha(image),sdk_manifest_sha256=sha(sdk/'manifest.json'))
        if sha(image)!=manifest['artifacts']['xos.img']['sha256'] or sdk_manifest['build_id']!=manifest['build_id']:
            raise AssertionError('kernel/SDK receipt mismatch')
        source=ROOT/'tests/fixtures/dash_c1/pipe_atomic.c'
        for path in (source,Path(__file__).resolve(),ROOT/'src/kernel/arch/x86_64/tasks.cpp',
                     ROOT/'src/user/libc/newlib_syscalls.cpp',ROOT/'src/shared/include/xos/process_abi.hpp'):
            report['sources'][str(path.relative_to(ROOT))]=sha(path)
        captured=args.artifacts/'pipe_atomic.c';shutil.copy2(source,captured)
        if sha(captured)!=report['sources'][str(source.relative_to(ROOT))]:raise AssertionError('source changed during snapshot')
        shutil.copy2(Path(__file__).resolve(),args.artifacts/'runner_snapshot.py')
        cc=shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc';tools=ROOT/'build/target_tools'
        for name,path in [('gcc',Path(cc)),('as',tools/'as'),('ld',tools/'ld')]:
            report['tools'][name]={'path':str(path.resolve()),'sha256':sha(path),
                'version':subprocess.check_output([str(path),'--version'],text=True).splitlines()[0]}
        libgcc=Path(subprocess.check_output([cc,'-print-libgcc-file-name'],text=True).strip())
        report['libgcc_sha256']=sha(libgcc)
        report['sdk_inputs']={str(path.relative_to(sdk)):sha(path) for path in (
            sdk/'crt0_posix.o',sdk/'user.ld',sdk/'lib/libxos.a',sdk/'lib/libxos_loader.a',
            sdk/'lib/libc.a',sdk/'lib/libm.a',sdk/'include/xos/process_abi.hpp')}
        elf=args.artifacts/'pipe_atomic.elf'
        line=[cc,'-B'+str(tools)+'/','-std=gnu11','-O2','-g','-mno-red-zone','-fno-pie','-fno-pic',
              '-fno-stack-protector','-idirafter',str(sdk/'include'),'-nostdlib','-static','-no-pie',
              '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),
              str(sdk/'crt0_posix.o'),str(captured),'-Wl,--start-group',str(sdk/'lib/libxos.a'),
              str(sdk/'lib/libxos_loader.a'),str(sdk/'lib/libc.a'),str(sdk/'lib/libm.a'),str(libgcc),
              '-Wl,--end-group','-o',str(elf)]
        report['build_commands'].append(line)
        result=subprocess.run(line,capture_output=True,text=True)
        (args.artifacts/'compile_link.log').write_text(result.stdout+result.stderr)
        if result.returncode:raise AssertionError('probe build failed: '+str(result.returncode))
        report['probe']={'path':str(elf),'sha256':sha(elf),'bytes':elf.stat().st_size}
        with tempfile.TemporaryDirectory(prefix='xos_pipe_atomic_') as folder_name:
            folder=Path(folder_name);disk=folder/'work.img';private=folder/'boot.img'
            shutil.copyfile(image,private);create_fat32(disk,512)
            transfer(disk,'mkdir','/tests');transfer(disk,'import','/tests/pipe_atomic',elf)
            guest=Guest(private,'pipe_atomic_'+run_id[:12],work_disk=disk)
            report['qemu_command']=guest.command;qemu=Path(guest.command[0])
            report['tools']['qemu']={'path':str(qemu.resolve()),'sha256':sha(qemu),
                'version':subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0]}
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r')
            guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
            baseline=resources(guest);report['baseline_resources']=baseline
            report['guest_command']='exec-driver /tests/pipe_atomic'
            start=len(guest.output)
            output=command(guest,report['guest_command'],b'kind=exited code=',timeout=180)
            report['output']=output.decode(errors='replace')
            log=args.artifacts/'probe.serial.log';log.write_bytes(output)
            report['probe_serial_log']={'path':str(log),'sha256':sha(log)}
            if b'PIPE_ATOMIC_FAIL ' in output or b'kind=exited code=0' not in output:
                raise AssertionError('guest atomic-write probe failed')
            markers=(b'PIPE_ATOMIC_RAW minimum_validation=ok insufficient_space=EAGAIN whole_512=ok large_7777_short_4096=ok PASS',
                     b'PIPE_ATOMIC_WRITER A records=64 write_each=512 PASS',
                     b'PIPE_ATOMIC_WRITER B records=64 write_each=512 PASS')
            for marker in markers:
                if marker not in output:raise AssertionError('missing guest evidence: '+repr(marker))
            parent=re.search(rb'PIPE_ATOMIC_PARENT child_a=(\d+) child_b=(\d+) records_A=(\d+) records_B=(\d+) bytes=(\d+) read_calls=(\d+) read_chunk=257 eof=1 resource_baseline=ok PASS',output)
            if not parent or tuple(int(parent[i]) for i in (3,4,5))!=(64,64,65536):
                raise AssertionError('record counts or full stream comparison failed')
            report['actual']={'child_pids':[int(parent[1]),int(parent[2])],'records_A':int(parent[3]),
                'records_B':int(parent[4]),'bytes':int(parent[5]),'read_calls':int(parent[6]),'eof':True,
                'all_512_byte_records_uniform':True,'child_exit_codes':[0,0],'exit_code':0}
            counters=[]
            for phase,fields in re.findall(rb'PIPE_ATOMIC_RESOURCES (\S+) ([^\r\n]+)',output):
                counters.append({'phase':phase.decode(),**{key.decode():int(value) for key,value in re.findall(rb'(\w+)=(\d+)',fields)}})
            report['guest_resource_counters']=counters
            by_phase={entry['phase']:{key:value for key,value in entry.items() if key!='phase'} for entry in counters}
            if 'baseline' not in by_phase or by_phase.get('final')!=by_phase['baseline']:
                raise AssertionError('guest process/thread/page counters did not return to baseline')
            final=resources(guest);report['final_resources']=final
            if final!=baseline:raise AssertionError(f'supervisor counters drifted: {final} != {baseline}')
            report['checks']=['raw_wait_writer_minimum_and_read_argument_validation',
                'flagged_small_raw_write_returns_EAGAIN_until_all_512_bytes_fit',
                'unflagged_small_and_large_raw_writes_retain_legacy_short_write_behavior',
                'two_spawned_writers_inherit_same_stdout_pipe_and_each_write_returns_512',
                '257_byte_reads_and_yields_preserve_every_512_byte_A_or_B_record',
                '64_records_per_writer_65536_bytes_EOF_and_both_exit_zero',
                'guest_and_supervisor_resources_return_to_baseline']
            report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest is not None:report['output_tail']=bytes(guest.output[-20000:]).decode(errors='replace')
        raise
    finally:
        if guest is not None:
            log=args.artifacts/'all.serial.log';log.write_bytes(bytes(guest.output))
            report['serial_log']={'path':str(log),'sha256':sha(log)};guest.close()
        text=json.dumps(report,indent=2)+'\n';(args.artifacts/'report.json').write_text(text)
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(text)
    print(json.dumps(report))


if __name__=='__main__':main()
