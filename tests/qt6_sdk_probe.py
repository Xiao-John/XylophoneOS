# SPDX-License-Identifier: Apache-2.0
"""Run the pre-Qt C++ threading probe on an explicitly supplied XOS image.

This tests the SDK only; it is not a Qt or G01 qualification. The work disk is
new and disposable. Save serial bytes even when a check fails.
"""
import argparse
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

p = argparse.ArgumentParser()
p.add_argument('--image', type=Path, required=True)
p.add_argument('--payload', type=Path, required=True)
p.add_argument('--report', type=Path, required=True)
p.add_argument('--marker', default='[cppthread] thread mutex cond once retry TLS exception guard chrono=ok')
p.add_argument('--argument', default='', choices=['', 'quota'])
a = p.parse_args()
a.report.parent.mkdir(parents=True, exist_ok=True)
report = {'status': 'FAILED', 'image_sha256': hashlib.sha256(a.image.read_bytes()).hexdigest(),
          'elf_sha256': hashlib.sha256(a.payload.read_bytes()).hexdigest()}
guest = None
try:
    with tempfile.TemporaryDirectory(prefix='xos_qt_sdk_probe_') as tmp:
        disk = Path(tmp) / 'work.img'
        image = Path(tmp) / 'boot.img'
        shutil.copyfile(a.image, image)
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/cppthread.elf', a.payload)
        guest = Guest(image, 'qt6_sdk_probe', work_disk=disk)
        report['qemu_command'] = guest.command
        guest.expect(b'xos64> ', timeout=30)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=30)
        pump(guest, 1.5)
        before = resources(guest)
        output = command(guest, 'exec-file /bin/cppthread.elf' + (' ' + a.argument if a.argument else ''), b'kind=exited code=', timeout=90)
        assert b'kind=exited code=0' in output, output[-4000:]
        assert a.marker.encode() in output, output[-4000:]
        after = resources(guest)
        assert before == after, (before, after)
        report.update(status='PASSED', resources_before=before, resources_after=after)
finally:
    if guest:
        a.report.with_suffix('.serial.log').write_bytes(guest.output)
        guest.close()
    a.report.write_text(json.dumps(report, indent=2) + '\n')
print(report['status'])
