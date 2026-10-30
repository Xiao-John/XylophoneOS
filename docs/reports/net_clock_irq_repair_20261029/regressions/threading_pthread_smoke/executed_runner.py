# SPDX-License-Identifier: Apache-2.0
"""Qualified pthread/newlib payloads execute only inside a real XOS guest."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/threading_pthread_smoke')
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes, pump

def main():
    build = ROOT / 'build'
    report = {'kernel_build_id': json.loads((build/'manifest.json').read_text())['build_id'],
              'status': 'failed', 'checks': [], 'runs': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_pthread_') as folder:
            private = Path(folder); image = private/'boot.img'; disk = private/'work.img'
            shutil.copyfile(build/'xos.img', image); create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            payload = build/'threading_pthread_probe.elf'
            report['payload_sha256'] = hashlib.sha256(payload.read_bytes()).hexdigest()
            transfer(disk, 'import', '/bin/pthread.elf', payload)
            transfer(disk, 'import', '/bin/cthread.elf', build/'threading_c_probe.elf')
            guest = Guest(image, 'threading_pthread', work_disk=disk)
            guest.expect(b'xos64> ', timeout=30); send_bytes(guest,b'run\r')
            guest.expect_supervisor(trace=True, timeout=30); pump(guest,1.5)
            baseline = resources(guest); report['resources_before'] = baseline
            for mode, code in [('core',0),('core',0),('last',0),('exit',9),('quick',19),('recursive',23)]:
                output = command(guest, 'exec-file /bin/pthread.elf '+mode, b'kind=exited code=', timeout=90)
                assert f'kind=exited code={code}'.encode() in output, output[-4000:]
                assert b'[pthread] FAIL' not in output, output[-4000:]
                if mode == 'core':
                    assert b'mutex cond once TSS errno TLS malloc stdio files lifecycle=ok' in output, output[-4000:]
                if mode not in ['quick', 'recursive']:
                    assert output.count(b'[pthread] process-fini=1') == 1, output[-4000:]
                else:
                    assert b'process-fini=' not in output, output[-4000:]
                after = resources(guest); assert after == baseline, (baseline,after)
                report['runs'].append({'mode':mode,'code':code,'resources_after':after})
            report['checks'] = ['guest_pthread_mutex_cond_once_keys_four_rounds_tls_errno',
                'guest_concurrent_newlib_malloc_realloc_stdio_and_shared_file_session',
                'guest_shared_open_offset_dup_close_and_stack_query',
                'guest_monotonic_timeout_relocks_mutex_realtime_returns_ENOTSUP',
                'guest_last_thread_process_fini_once', 'guest_process_exit_stops_running_peer',
                'guest__exit_skips_callbacks', 'guest_recursive_exit_during_TLS_cleanup_does_not_hang', 'guest_process_resources_return_to_baseline']
            output = command(guest, 'exec-file /bin/cthread.elf', b'kind=exited code=', timeout=30)
            assert b'[cthread] C ABI TLS errno join=ok' in output and b'kind=exited code=0' in output, output[-4000:]
            assert resources(guest) == baseline
            report['checks'].append('guest_plain_C_consumer_ABI')
            command(guest,'sync',b'[files] sync=ok'); report['status']='passed'
            print(f"PASS {len(report['checks'])} pthread groups | kernel {report['kernel_build_id']}")
    except Exception as error:
        report['error']=str(error); raise
    finally:
        if guest: guest.close()
        (build/'threading_pthread_report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__ == '__main__': main()
