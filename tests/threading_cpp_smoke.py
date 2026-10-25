# SPDX-License-Identifier: Apache-2.0
"""Qualified pthread/newlib payloads execute only inside a real XOS guest."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
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
            payload = build/'threading_cpp_probe.elf'
            report['payload_sha256'] = hashlib.sha256(payload.read_bytes()).hexdigest()
            transfer(disk, 'import', '/bin/cppthread.elf', payload)
            transfer(disk, 'import', '/bin/legacy.elf', build/'threading_legacy.elf')
            guest = Guest(image, 'threading_cpp', work_disk=disk)
            guest.expect(b'xos64> ', timeout=30); send_bytes(guest,b'run\r')
            guest.expect_supervisor(trace=True, timeout=30); pump(guest,1.5)
            baseline = resources(guest); report['resources_before'] = baseline
            for iteration in range(3):
                output = command(guest, 'exec-file /bin/cppthread.elf', b'kind=exited code=', timeout=90)
                assert b'kind=exited code=0' in output, output[-4000:]
                assert b'[cppthread] thread mutex cond once retry TLS exception guard chrono=ok' in output, output[-4000:]
                after = resources(guest); assert after == baseline, (baseline, after)
                report['runs'].append({'iteration':iteration,'resources_after':after})
            report['checks'] = ['guest_std_thread_join', 'guest_std_mutex_condition_variable',
                'guest_call_once_exception_retry', 'guest_CXX_static_guard_once',
                'guest_thread_local_destructors', 'guest_concurrent_CXX_exceptions',
                'guest_steady_clock_wait_for_nanosleep', 'guest_process_resources_return_to_baseline']
            output = command(guest, 'exec-file /bin/cppthread.elf wallclock', b'kind=faulted', timeout=30)
            assert b'vector=6' in output and resources(guest) == baseline, output[-4000:]
            report['checks'].append('guest_unsupported_system_clock_terminates_explicitly')
            output = command(guest, 'exec-file /bin/legacy.elf', b'kind=exited code=', timeout=30)
            assert b'legacy-arena-explicitly-rejected' in output and b'kind=exited code=0' in output, output[-4000:]
            assert resources(guest) == baseline
            report['checks'].append('guest_legacy_ELF_layout_remains_loadable_thread_opt_in_rejects_overlap')
            command(guest,'sync',b'[files] sync=ok'); report['status']='passed'
            print(f"PASS {len(report['checks'])} C++ threading groups | kernel {report['kernel_build_id']}")
    except Exception as error:
        report['error']=str(error); raise
    finally:
        if guest: guest.close()
        (build/'threading_cpp_report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__ == '__main__': main()
