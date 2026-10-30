# SPDX-License-Identifier: Apache-2.0
"""New guest observations, never a rebinding of a prior qualification."""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes, pump
from work_disk import transfer

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--js-elf', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    disk = out / 'work.img'
    create_fat32(disk, 512)
    for name in ['/usr', '/usr/bin', '/work', '/work/probes']:
        transfer(disk, 'mkdir', name)
    strip_command = ['x86_64-elf-strip', '-o', str(out / 'jsprobe'), str(args.js_elf.resolve())]
    subprocess.run(strip_command, check=True)
    transfer(disk, 'import', '/usr/bin/jsprobe', out / 'jsprobe')
    fixtures = ROOT / 'tests/fixtures/modern2_runtime'
    inputs = {}
    for path in sorted(fixtures.iterdir()):
        if path.suffix in {'.js', '.mjs'}:
            transfer(disk, 'import', '/work/probes/' + path.name, path)
            inputs[str(path.relative_to(ROOT))] = sha(path)
    report = {'status': 'FAILED', 'scope': 'QuickJS embedding language and missing Web APIs; not V8 or browser acceptance',
              'image_sha256': sha(args.image), 'elf_sha256': sha(args.js_elf),
              'stripped_sha256': sha(out / 'jsprobe'), 'fixture_sha256': inputs,
              'disk_before_sha256': sha(disk), 'strip_command': strip_command, 'checks': []}
    cases = [
        ('buffers.js', 'BUFFER_LANGUAGE_OK', '0', 'PASSED_LANGUAGE_ONLY'),
        ('promises.js', 'JS_PROMISE_FULFILLED:PROMISE_JOBS_DONE', '0', 'PASSED_LANGUAGE_ONLY'),
        ('module.mjs', 'JS_PROMISE_FULFILLED:undefined', '0', 'PASSED_SINGLE_MODULE_ONLY'),
        ('pending.mjs', 'JS_PROMISE_PENDING', '1', 'PASSED_PENDING_REJECTION_CONTROL'),
        ('rejected.js', 'CONTROL_REJECTED_PROMISE', '1', 'PASSED_REJECTION_CONTROL'),
        ('async_failure.js', 'CONTROL_ASYNC_ASSERTION', '1', 'PASSED_JOB_DRAIN_CONTROL'),
        ('import.mjs', 'could not load module', '1', 'FAILED_MODULE_LOADER'),
        ('dom.js', "'document' is not defined", '1', 'FAILED_MISSING_WEB_API'),
        ('events.js', "'EventTarget' is not defined", '1', 'FAILED_MISSING_WEB_API'),
        ('worker.js', "'Worker' is not defined", '1', 'FAILED_MISSING_WEB_API'),
        ('wasm.js', "'WebAssembly' is not defined", '1', 'FAILED_MISSING_WEB_API'),
        ('origin.js', "'location' is not defined", '1', 'FAILED_NO_ORIGIN_MODEL'),
        ('globals.js', 'JS_RESULT:{', '0', 'OBSERVATION_ONLY'),
        ('buffers.js', 'BUFFER_LANGUAGE_OK', '0', 'PASSED_RECOVERY_ONLY'),
    ]
    guest = None
    try:
        guest = Guest(args.image.resolve(), 'modern2_runtime_' + out.name, work_disk=disk)
        report['qemu_command'] = guest.command
        report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
        guest.expect(b'xos64> ', timeout=30)
        start = len(guest.output)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, start=start, timeout=40)
        start = len(guest.output)
        send_bytes(guest, b'demo quiet\r')
        guest.expect(b'demo tasks', start=start, timeout=20)
        guest.expect_supervisor(start=start, timeout=20)
        pump(guest, .3)
        baseline = resources(guest)
        report['resources_before'] = baseline
        for index, (file, marker, code, capability) in enumerate(cases):
            start = len(guest.output)
            command = 'jsprobe /work/probes/' + file
            send_bytes(guest, command.encode() + b'\r')
            guest.expect(b'[wait] pid=', start=start, timeout=60)
            guest.expect_supervisor(start=guest.output.find(b'[wait] pid=', start), timeout=20)
            pump(guest, .1)
            output = re.sub(r'\x1b\[[0-9;]*m', '', bytes(guest.output[start:]).decode('utf-8', 'replace'))
            after = resources(guest)
            (out / f'{index:02}_{file}.log').write_text(output)
            report['checks'].append({'file': file, 'command': command, 'capability_status': capability,
                'harness_status': 'PASSED' if marker in output and 'kind=exited code=' + code in output and baseline == after else 'FAILED',
                'expected_marker': marker, 'expected_exit': code, 'resources_after': after})
        report['resources_after'] = resources(guest)
        report['status'] = 'PASSED' if all(x['harness_status'] == 'PASSED' for x in report['checks']) else 'FAILED'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if guest:
            guest.close()
            for kind in ['serial', 'qemu']:
                data = (ROOT / f'build/{guest.name}_{kind}.log').read_bytes()
                (out / f'{kind}.log.gz').write_bytes(gzip.compress(data, mtime=0))
        report['disk_after_sha256'] = sha(disk)
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    raise SystemExit(report['status'] != 'PASSED')

if __name__ == '__main__':
    main()
