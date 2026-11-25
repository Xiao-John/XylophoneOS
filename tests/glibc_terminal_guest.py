#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise public glibc terminal interfaces through real authorized terminal v2 channels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from build_glibc_sdk import inputs as glibc_inputs
from dash_c3_exec_smoke import exec_opt_in
from glibc_g1_probe import clean_build_environment
from glibc_static_guest import system_sources, sha
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from terminal_observation_sector import observation_record, prepare_observations
from work_disk import transfer


def tty_opt_in(path):
    data=path.read_bytes()
    offset=struct.unpack_from('<Q',data,40)[0]
    size,count,names_index=struct.unpack_from('<HHH',data,58)
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(count)]
    names_header=sections[names_index];names=data[names_header[4]:names_header[4]+names_header[5]]
    found=[]
    for section in sections:
        if names[section[0]:].split(b'\0',1)[0]!=b'.xos.tty':continue
        if section[1]!=1 or section[2]&3!=2 or section[5]!=16:
            raise RuntimeError('terminal marker must be one 16-byte read-only ALLOC PROGBITS section')
        if struct.unpack_from('<QII',data,section[4])!=(0x31595454534f5858,1,16):
            raise RuntimeError('invalid terminal ABI marker')
        phoff=struct.unpack_from('<Q',data,32)[0];phsize,phcount=struct.unpack_from('<HH',data,54)
        for i in range(phcount):
            ph=struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize)
            if ph[0]==1 and ph[1]&6==4 and ph[3]<=section[3] and section[3]+16<=ph[3]+ph[5] and ph[2]+section[3]-ph[3]==section[4]:
                found.append({'address':section[3],'offset':section[4],'load_flags':ph[1]})
    if len(found)!=1:raise RuntimeError('terminal marker lacks one read-only load mapping')
    return found[0]


def release_blocked_reader(guest, start, report, repetition, disk, observation, timeout=60):
    expected=observation_record(observation['nonce'])
    deadline=time.monotonic()+timeout
    # No FAT lookup/export or host write is permitted after QEMU starts.
    with disk.open('rb',buffering=0) as stream:
        while True:
            stream.seek(observation['offset']);actual=stream.read(512)
            if actual==expected:break
            captured=bytes(guest.output[start:])
            if guest.process.poll() is not None or b'GLIBC_TERMINAL_FAIL' in captured or b'kind=exited code=' in captured:
                raise RuntimeError('terminal probe stopped before the complete observation record')
            if time.monotonic()>=deadline:
                raise AssertionError('blocked-reader file-progress record timed out; input withheld')
            pump(guest,0.025)
    if b'GLIBC_TERMINAL_BLOCK_PASS' in guest.output[start:]:raise RuntimeError('blocking read completed before input')
    report['input_events'].append({'repetition':repetition,'input_hex':'1b5b41',
                                   'after':'complete_fresh_observation_record','serial_offset':len(guest.output),
                                   'before_threads':2,'before_waiting':1,'after_threads':2,'after_waiting':1,
                                   'file_progress':1,'record_sha256':hashlib.sha256(actual).hexdigest(),
                                   'observation':observation})
    send_bytes(guest,b'\x1b[A')


def build_parent(system,output,report):
    sdk=system/'sdk';source=ROOT/'tests/fixtures/glibc_g3/terminal_exec_parent.c'
    binary=output/'terminal_parent.elf';obj=output/'terminal_parent.o'
    env,removed=clean_build_environment(os.environ);env['LC_ALL']='C'
    compiler=Path(shutil.which('x86_64-elf-gcc')).resolve(strict=True)
    libgcc=Path(subprocess.check_output([compiler,'-print-libgcc-file-name'],env=env,text=True).strip())
    headers=subprocess.check_output([compiler,'-print-file-name=include'],env=env,text=True).strip()
    inputs=[sdk/name for name in ('crt0_posix.o','user.ld','lib/libxos.a','lib/libxos_loader.a','lib/libc.a','lib/libm.a')]
    before={str(p.relative_to(sdk)):sha(p) for p in inputs}
    calls=[[str(compiler),'-std=gnu11','-O2','-g','-mno-red-zone','-fno-pie','-fno-pic','-fno-stack-protector','-fno-builtin','-nostdinc',
            '-isystem',str(sdk/'include'),'-isystem',headers,'-c',str(source),'-o',str(obj)],
           [str(compiler),'-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
            '-T',str(sdk/'user.ld'),str(sdk/'crt0_posix.o'),str(obj),'-Wl,--start-group',*map(str,inputs[2:]),str(libgcc),'-Wl,--end-group','-o',str(binary)]]
    with (output/'terminal_parent_build.log').open('w') as log:
        for call in calls:subprocess.run(call,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    if before!={str(p.relative_to(sdk)):sha(p) for p in inputs}:raise RuntimeError('native SDK changed during parent build')
    report['elfs']['terminal_parent']={'source_sha256':sha(source),'elf_sha256':sha(binary),'commands':calls,
                                      'sdk_inputs':before,'libgcc_sha256':sha(libgcc),'compiler_sha256':sha(compiler),
                                      'sanitized_environment':removed,'tty_marker':tty_opt_in(binary)}
    return binary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build',type=Path,required=True)
    parser.add_argument('--glibc-build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repetitions',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repetitions<=10:parser.error('repetitions must be 1..10')
    output=args.output.absolute();output.mkdir(parents=True,exist_ok=False)
    report={'status':'not_run','suite':'glibc_terminal','runs':[],'input_events':[],'qmp':'disabled; serial-only',
            'not_run':['hardware UART timing','continuous-input flush race','glibc outgoing terminal fork/exec/spawn',
                       'same-session full-duplex I/O','dash launch entry','service death during guest I/O']}
    guest=None
    try:
        system_build=args.system_build.resolve(strict=True);glibc_build=args.glibc_build.resolve(strict=True)
        system_path=system_build/'manifest.json';sdk_path=glibc_build/'manifest.json'
        system=json.loads(system_path.read_text());sdk=json.loads(sdk_path.read_text());sysroot=glibc_build/'sysroot'
        if sdk.get('status')!='static_sdk_built':raise RuntimeError('complete static SDK required')
        initial_system=sha(system_path);initial_sdk=sha(sdk_path)
        def verify():
            if initial_system!=sha(system_path) or initial_sdk!=sha(sdk_path):raise RuntimeError('manifest changed')
            if system_sources()!=system['sources'] or glibc_inputs()!=sdk['inputs']:raise RuntimeError('source snapshot changed')
            for name,info in system['artifacts'].items():
                if sha(system_build/name)!=info['sha256']:raise RuntimeError('system artifact changed: '+name)
            for name,digest in sdk['artifacts'].items():
                if sha(sysroot/name)!=digest:raise RuntimeError('SDK artifact changed: '+name)
        verify()
        report.update(system_build_id=system['build_id'],system_manifest_sha256=initial_system,
                      glibc_manifest_sha256=initial_sdk,image_sha256=sha(system_build/'xos-install.iso'),
                      runner_sha256=sha(Path(__file__).resolve()),elfs={})
        programs={}
        for name,defines in [('terminal_probe',[]),('terminal_receiver',['XOS_GLIBC_TERMINAL_EXEC_RECEIVER'])]:
            source=ROOT/'tests/fixtures/glibc_g3/terminal_public_probe.c';binary=output/(name+'.elf')
            call=[sys.executable,str(ROOT/'scripts/build_glibc_program.py'),'--sdk',str(sysroot),'--source',str(source),'--output',str(binary)]
            for define in defines:call+=['--define',define]
            with (output/(name+'_build.log')).open('w') as log:subprocess.run(call,stdout=log,stderr=subprocess.STDOUT,check=True)
            report['elfs'][name]={'source_sha256':sha(source),'elf_sha256':sha(binary),'command':call,
                                  'tty_marker':tty_opt_in(binary),'exec_marker':exec_opt_in(binary)}
            if defines and not report['elfs'][name]['exec_marker']:raise RuntimeError('receiver marker missing')
            programs[name]=binary
        programs['terminal_parent']=build_parent(system_build,output,report)
        verify();report['status']='running'
        with tempfile.TemporaryDirectory(prefix='xos_glibc_terminal_') as temporary:
            disk=Path(temporary)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin')
            for name,binary in programs.items():transfer(disk,'import','/bin/'+name,binary)
            transfer(disk,'import','/bin/terminal.elf',system_build/'user_terminal.image.elf')
            observations=prepare_observations(disk,args.repetitions)
            report['observations']=observations;report['work_disk_initial_sha256']=sha(disk)
            guest=Guest(system_build/'xos-install.iso','glibc_terminal',work_disk=disk,iso=True,qmp_enabled=False)
            report['qemu_command']=guest.command
            report['qemu_version']=subprocess.check_output([guest.command[0],'--version'],text=True).splitlines()[0]
            guest.expect(b'xos64> ',timeout=30);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=30)
            command(guest,'demo quiet',b'demo tasks');report['before_terminal']=resources(guest)
            warmup=command(guest,'tty-run /bin/terminal_probe warmup',b'kind=exited code=',timeout=90)
            if b'GLIBC_TERMINAL_WARMUP_PASS' not in warmup or re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)',warmup)!=[b'0']:
                raise RuntimeError('authorized terminal warmup failed: '+repr(warmup))
            baseline=resources(guest);report['baseline_with_service']=baseline
            for repetition in range(args.repetitions):
                observation=observations[repetition]
                start=len(guest.output)
                send_bytes(guest,('tty-run /bin/terminal_probe '+observation['path']+' '+observation['nonce']+'\r').encode())
                guest.expect(b'GLIBC_TERMINAL_BLOCK_READY',start=start,timeout=60)
                release_blocked_reader(guest,start,report,repetition+1,disk,observation)
                for ready,value in [(b'GLIBC_TERMINAL_FLUSH_QUEUE_READY',b'Q'),(b'GLIBC_TERMINAL_FLUSH_FRESH_READY',b'F'),
                                    (b'GLIBC_TERMINAL_TCSA_QUEUE_READY',b'X'),(b'GLIBC_TERMINAL_TCSA_FRESH_READY',b'N')]:
                    guest.expect(ready,start=start,timeout=60);send_bytes(guest,value)
                guest.expect(b'kind=exited code=',start=start,timeout=60);guest.expect(b'xsh> ',start=start,timeout=30)
                captured=bytes(guest.output[start:])
                markers=[b'GLIBC_TERMINAL_MODE_PASS',b'GLIBC_TERMINAL_BLOCK_PASS',b'GLIBC_TERMINAL_WRITE_PASS',
                         b'GLIBC_TERMINAL_FLUSH_PASS',b'GLIBC_TERMINAL_PASS']
                position=0
                for marker in markers:
                    found=captured.find(marker,position)
                    if found<0:raise RuntimeError('missing terminal marker: '+repr(marker)+' '+repr(captured))
                    position=found+len(marker)
                if re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)',captured)!=[b'0']:raise RuntimeError('terminal probe exit: '+repr(captured))
                after=resources(guest)
                if after!=baseline:raise RuntimeError('terminal resource drift: '+repr((baseline,after)))
                report['runs'].append({'case':'public_terminal','repetition':repetition+1,'status':'passed','resources':after,'output':captured.decode(errors='replace')})
                captured=command(guest,'tty-run /bin/terminal_parent /bin/terminal_receiver',b'kind=exited code=',timeout=90)
                if re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)',captured)!=[b'0'] or b'GLIBC_TERMINAL_PARENT_READY' not in captured or b'GLIBC_TERMINAL_INHERIT_PASS' not in captured:
                    raise RuntimeError('terminal exec receiver failed: '+repr(captured))
                after=resources(guest)
                if after!=baseline:raise RuntimeError('exec terminal resource drift: '+repr((baseline,after)))
                report['runs'].append({'case':'native_exec_terminal_receiver','repetition':repetition+1,'status':'passed','resources':after,'output':captured.decode(errors='replace')})
                (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            verify()
            for name,binary in programs.items():
                if sha(binary)!=report['elfs'][name]['elf_sha256']:raise RuntimeError('ELF changed during guest')
            report['status']='passed_subset'
    except Exception as error:
        report['error']=str(error)
        if guest is not None:report['status']='failed'
        raise
    finally:
        if guest is not None:
            guest.close();(output/'serial.log').write_bytes(guest.output);report['serial_sha256']=sha(output/'serial.log')
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS glibc terminal: authorized channels, termios/ioctl, blocking I/O, exec sequence, resources')


if __name__=='__main__':main()
