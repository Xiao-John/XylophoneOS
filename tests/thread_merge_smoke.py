# SPDX-License-Identifier: Apache-2.0
"""Targeted integration gate: merged thread lifecycle + B2 FD ordering + ISO sys53.
Not the PR's full T2 qualification or a replacement for B2 acceptance.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command,resources
from task_smoke import send_bytes,pump
from dash_b2_smoke import build_probe
from xypm_format import canonical,sha_file


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',type=Path,required=True)
    parser.add_argument('--dash-manifest',type=Path,required=True)
    parser.add_argument('--iso-only',action='store_true')
    args=parser.parse_args();system=args.system.resolve();dash=json.loads(args.dash_manifest.read_text())
    metadata=json.loads((system/'manifest.json').read_text());binary=ROOT/dash['elf']
    assert sha_file(binary)==dash['sha256']
    report={'status':'failed','system_build_id':metadata['build_id'],'image_sha256':sha_file(system/'xos.img'),
            'dash_sha256':dash['sha256'],'checks':[],'not_run':['full_threaded_newlib_CXX_SDK_requalification','B2_full_native_compiler_chain']}
    if args.iso_only:
        previous=json.loads((system/'merge_report.json').read_text())
        assert previous['image_sha256']==report['image_sha256'] and previous['dash_sha256']==report['dash_sha256']
        assert len(previous['checks'])==6
        report['checks']=previous['checks'];report['baseline']=previous['baseline']
    helper=ROOT/'build/work_disk_host';guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_thread_merge_') as folder:
            folder=Path(folder)
            if not args.iso_only:
                folder=Path(folder);disk=folder/'work.img';create_fat32(disk,512)
                def transfer(op,name,source=None):
                    args=[str(helper),str(disk),op,name]
                    if source is not None:args.append(str(source))
                    subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
                for name in ('/usr','/usr/bin','/bin','/tests','/out','/tmp'):transfer('mkdir',name)
                transfer('import','/usr/bin/dash',binary)
                transfer('import','/bin/threading.elf',system/'user_threading_core_probe.image.elf')
                transfer('import','/bin/child.elf',system/'user_demo.image.elf')
                for name,source in [('cat',ROOT/'src/ports/sbase/xos/cat.c'),
                                    ('stdio_probe',ROOT/'tests/fixtures/dash_b2/stdio_probe.c'),
                                    ('spin',ROOT/'tests/fixtures/dash_b2/spin.c')]:
                    target=folder/name;build_probe(source,target,system/'sdk')
                    transfer('import','/usr/bin/cat' if name=='cat' else '/out/'+name,target)
                transfer('import','/tests/b2.sh',ROOT/'tests/fixtures/dash_b2/b2.sh')
                # Explicit spawn actions exercise the private snapshot, including shared handles.
                source=folder/'spawn.c'
                source.write_text('''#include <spawn.h>
    #include <fcntl.h>
    #include <sys/wait.h>
    #include <unistd.h>
    int main(void) {
     posix_spawn_file_actions_t a;
     if(posix_spawn_file_actions_init(&a))return 1;
     if(posix_spawn_file_actions_addopen(&a,1,"/out/actions.txt",O_CREAT|O_TRUNC|O_WRONLY,0))return 2;
     if(posix_spawn_file_actions_adddup2(&a,1,2))return 3;
     char *args[]={"/out/stdio_probe",0};pid_t pid;int status;
     int e=posix_spawn(&pid,args[0],&a,0,args,0);
     posix_spawn_file_actions_destroy(&a);
     if(e||waitpid(pid,&status,0)!=pid||status)return 4;
     if(write(1,"SNAPSHOT_STDOUT_OK\\n",19)!=19)return 5;
     return 0;
    }''')
                probe=folder/'spawn';build_probe(source,probe,system/'sdk');transfer('import','/out/spawn',probe)
                guest=Guest(system/'xos.img','thread_merge',work_disk=disk)
                guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
                baseline=resources(guest);report['baseline']=baseline
                for mode,marker in [('core',b'shared stack tls fpu preempt prepare rollback join detach wait timeout pins=ok'),
                                    ('last',b'last-thread-cleanup'),('arbitration',b'last-arbitration-stopped-peer=ok')]:
                    output=command(guest,'exec-file /bin/threading.elf '+mode,b'kind=exited code=0',timeout=60)
                    assert marker in output and b'[threading] FAIL' not in output,output[-4000:]
                    assert resources(guest)==baseline
                    report['checks'].append('thread_'+mode)
                output=command(guest,'exec-driver /out/spawn',b'kind=exited code=0',timeout=60)
                assert b'SNAPSHOT_STDOUT_OK' in output,output[-2000:]
                output=command(guest,'exec-file /usr/bin/cat /out/actions.txt',b'kind=exited code=0',timeout=60)
                assert b'OUT\nERR\n' in output,output[-2000:]
                assert resources(guest)==baseline;report['checks'].append('spawn_private_ordered_actions')
                output=command(guest,'dash /tests/b2.sh',b'kind=exited code=0',timeout=90)
                for marker in (b'alpha\nbeta\n',b'OUT\nERR\n',b'order_two_start',b'order_two_end',
                               b'inside_builtin\n',b'restoration_marker',b'expected_redirection_failure',b'b2=ok'):
                    assert marker in output,(marker,output[-5000:])
                start=output.index(b'order_two_start');end=output.index(b'order_two_end',start)
                assert b'ERR\n' in output[start:end] and b'unexpected_redirection_success' not in output
                assert resources(guest)==baseline;report['checks'].append('B2_order_dup_append_input_builtin_restore')
                send_bytes(guest,b'dash -i\r');guest.expect(b'$ ',timeout=30)
                start=len(guest.output);send_bytes(guest,b'/out/spin\r');pump(guest,0.5);send_bytes(guest,b'\x1b')
                guest.expect(b'$ ',start=start,timeout=30);assert b'cancelled_by_escape' in guest.output[start:]
                send_bytes(guest,b'exit\r');guest.expect_supervisor(timeout=30)
                assert resources(guest)==baseline;report['checks'].append('thread_model_nested_Escape')
                command(guest,'sync',b'[files] sync=ok',timeout=30)
                guest.close();(system/'merge_serial.log').write_bytes(guest.output);guest=None
            # Build ISO directly from isolated artifacts, without changing default run/install targets.
            iso=system/'merge-install.iso'
            empty=system/'merge_empty_kernel.bin';empty.write_bytes(b'')
            subprocess.run([sys.executable,str(ROOT/'scripts/make_iso.py'),'--boot',str(system/'boot_sector_iso.bin'),
                            '--loader',str(system/'kernel_loader_iso_file.bin'),'--kernel',str(empty),'--output',str(iso),
                            '--file','KERNEL.BIN='+str(system/'kernel.bin'),'--file','DASH.ELF='+str(binary)],check=True,stdout=subprocess.DEVNULL)
            fresh=folder/'iso_work.img';create_fat32(fresh,512)
            guest=Guest(iso,'thread_merge_iso',iso=True,work_disk=fresh)
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(timeout=40)
            guest.expect(b'[files] dash installed',timeout=40)
            start=len(guest.output);send_bytes(guest,b'dash -i\r');guest.expect(b'$ ',start=start,timeout=40)
            send_bytes(guest,b'exit\r');guest.expect_supervisor(timeout=40)
            report['checks'].append('ISO_sys53_dash_payload');report['iso_sha256']=sha_file(iso)
            report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        if guest:guest.close();(system/'merge_last_serial.log').write_bytes(guest.output)
        (system/'merge_report.json').write_bytes(canonical(report))
    print(canonical(report).decode())
if __name__=='__main__':main()
