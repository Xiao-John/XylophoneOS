# SPDX-License-Identifier: Apache-2.0
"""E08-1: native guest file sessions, large ELF, FAT32 sizes, streaming and reboot."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command,resources


def boot(disk,name):
    g=Guest(ROOT/'build/xos.img',name,work_disk=disk)
    g.expect(b'xos64> ',timeout=25)
    start=len(g.output)
    send_bytes(g,b'run\r')
    g.expect_supervisor(trace=True,start=start,timeout=25)
    # Allow the normal automatic retirement; this is not an E03 fixture run.
    pump(g,1.5)
    return g


def execute(g,args='',timeout=60):
    start=len(g.output)
    send_bytes(g,('exec-file /bin/e08_probe.elf'+(' '+args if args else '')+'\r').encode())
    g.expect(b'kind=exited code=',start=start,timeout=timeout)
    g.expect(b'sup> ',start=start,timeout=timeout)
    output=bytes(g.output[start:])
    if b'kind=exited code=0' not in output: raise AssertionError(output[-1200:])
    return output


def main():
    build=ROOT/'build'
    manifest=json.loads((build/'manifest.json').read_text())
    report={'build_id':manifest['build_id'],'checks':[],'status':'failed','measurements':[]}
    g=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_e08_') as folder:
            base=Path(folder)
            source=base/'source.txt';source.write_bytes(b'XOS source remains on the work disk.\n')
            payload=base/'payload.bin'; payload.write_bytes(bytes(range(256))*32768)
            expected=2166136261
            for byte in payload.read_bytes(): expected=((expected^byte)*16777619)&0xffffffff
            probe=build/'user_e08_probe.image.elf'
            assert probe.stat().st_size>131072
            report['probe']={'bytes':probe.stat().st_size,'sha256':hashlib.sha256(probe.read_bytes()).hexdigest()}
            for mib in (512,2048):
                disk=base/f'work_{mib}.img';create_fat32(disk,mib)
                for path in ('/bin','/src','/out','/tmp','/sysroot'):
                    transfer(disk,'mkdir',path)
                transfer(disk,'import','/bin/e08_probe.elf',probe)
                transfer(disk,'import','/src/long_source_name.txt',source)
                transfer(disk,'import','/src/throughput_payload.bin',payload)
                bad=base/f'bad{mib}.elf'; data=bytearray(probe.read_bytes());data[0]=0;bad.write_bytes(data)
                transfer(disk,'import','/bin/bad_probe.elf',bad)
                g=boot(disk,f'e08_{mib}_boot1')
                before=resources(g)
                # Read-only ATA/file benchmark at both capacity candidates.
                mark=len(g.output)
                send_bytes(g,b'exec-file /bin/e08_probe.elf bench\r')
                g.expect(b'[e08] ata-start',start=mark,timeout=30)
                raw_start=time.monotonic()
                g.expect(b'[e08] ata-done',start=mark,timeout=60)
                raw_seconds=time.monotonic()-raw_start
                g.expect(b'[e08] bench-start',start=mark,timeout=30)
                file_start=time.monotonic()
                g.expect(b'[e08] bench-done',start=mark,timeout=120)
                elapsed=time.monotonic()-file_start
                g.expect(b'kind=exited code=0',start=mark,timeout=15)
                g.expect(b'sup> ',start=mark,timeout=15)
                bench=bytes(g.output[mark:])
                if f'bench-done bytes={payload.stat().st_size} hash={expected}'.encode() not in bench:
                    raise AssertionError('guest throughput payload corrupted')
                report['measurements'].append({'disk_mib':mib,'raw_ata_read_seconds':raw_seconds,'raw_ata_mib_per_second':8/raw_seconds,
                                               'file_read_seconds':elapsed,
                                               'file_mib_per_second_lower_bound':8/elapsed})
                result=execute(g)
                if b'large-elf bss=ok path=ok stream=262144 sync=ok' not in result: raise AssertionError(result)
                if resources(g)!=before: raise AssertionError('guest page/task/completion leak')
                report['checks'].append(f'{mib}mib_large_elf_paths_stream_sync_resource_reclaim')
                command(g,'exec-file /bin/bad_probe.elf',b'elf: rejected reason=header')
                if resources(g)!=before: raise AssertionError('invalid ELF changed resources')
                report['checks'].append(f'{mib}mib_malformed_large_elf_rejected_without_resources')
                if mib==2048:
                    start=len(g.output)
                    send_bytes(g,b'spawn-file /bin/e08_probe.elf abandon\r')
                    g.expect(b'[e08] abandoned-ready',start=start,timeout=30)
                    g.expect(b'sup> ',start=start,timeout=15)
                    launched=bytes(g.output[start:])
                    pid=int(re.search(rb'\[loader\] started pid=(\d+)',launched).group(1))
                    # Parent and child issue RPC against independent response queues.
                    command(g,'cat /src/long_source_name.txt',b'XOS source remains')
                    edit_start=len(g.output)
                    send_bytes(g,b'edit contested.txt\r')
                    g.expect(b'(new)',start=edit_start,timeout=15)
                    send_bytes(g,b'new contents\r:w\r')
                    g.expect(b'[files] save error=-5',start=edit_start,timeout=15)
                    g.expect(b'[edit] buffer retained',start=edit_start,timeout=15)
                    send_bytes(g,b':q!\r');g.expect(b'sup> ',start=edit_start,timeout=15)
                    command(g,f'kill {pid}',b'kill: accepted')
                    command(g,f'wait {pid}',b'kind=killed code=-9')
                    execute(g)
                    if resources(g)!=before: raise AssertionError('concurrent session leaked resources')
                    report['checks'].append('independent_live_sessions_cannot_steal_staging_or_responses')
                    # Foreground cancellation leaves an open and partial staging;
                    # next client reuses a slot with a new PID and must recover.
                    start=len(g.output)
                    send_bytes(g,b'exec-file /bin/e08_probe.elf abandon\r')
                    g.expect(b'[e08] abandoned-ready',start=start,timeout=30)
                    send_bytes(g,b'\x1b')
                    g.expect(b'kind=killed code=-27',start=start,timeout=15)
                    g.expect(b'sup> ',start=start,timeout=15)
                    execute(g)
                    if resources(g)!=before: raise AssertionError('cancelled session leaked pages')
                    report['checks'].append('killed_client_open_and_staging_reclaimed_on_slot_reuse')
                    # Full page cap: 256 MiB plus all page tables, exact rollback.
                    pressure_start=time.monotonic()
                    pressure=command(g,'primtest',b'rollback=stable',timeout=120)
                    if b'page_pressure=65536' not in pressure: raise AssertionError('did not reach cap')
                    if resources(g)!=before: raise AssertionError('large address space rollback leaked')
                    report['measurements'].append({'page_pressure_pages':65536,'host_seconds':time.monotonic()-pressure_start})
                    report['checks'].append('256mib_page_cap_and_page_tables_reclaimed')
                command(g,'sync',b'[files] sync=ok')
                g.close();g=None
                exported=base/f'exported_{mib}.bin'
                transfer(disk,'export','/out/long_result_name.txt',exported)
                if exported.read_bytes()!=bytes(((i*17+3)&255) for i in range(262144)):
                    raise AssertionError('host independent disk read differs')
                g=boot(disk,f'e08_{mib}_boot2')
                execute(g,'verify')
                report['checks'].append(f'{mib}mib_reboot_preserves_large_file_and_elf')
                g.qmp('screendump',{'filename':str(build/f'e08_{mib}_screen.ppm')})
                g.close();g=None
            report['status']='passed'
            print(f"PASS: {len(report['checks'])} E08-1 groups | build {manifest['build_id']}")
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        if g is not None:g.close()
        (build/'e08_storage_smoke_report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
