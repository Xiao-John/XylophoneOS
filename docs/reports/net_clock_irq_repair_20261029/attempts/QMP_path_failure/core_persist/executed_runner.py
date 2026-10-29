# SPDX-License-Identifier: Apache-2.0
"""Run a Qt ELF, sync a private FAT disk, reboot, and verify via the Qt ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/final_runs/core_persist')
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
a = p.parse_args()
a.report.parent.mkdir(parents=True, exist_ok=True)
report = {'status': 'FAILED', 'image_sha256': hashlib.sha256(a.image.read_bytes()).hexdigest(),
          'elf_sha256': hashlib.sha256(a.payload.read_bytes()).hexdigest(), 'runs': []}
try:
    with tempfile.TemporaryDirectory(prefix='xos_qt_persist_') as temp:
        disk = Path(temp) / 'work.img'
        image = Path(temp) / 'boot.img'
        shutil.copyfile(a.image, image)
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        transfer(disk, 'import', '/bin/qtcore.elf', a.payload)
        for run, arg, marker in [(0, '', b'QT_CORE_EXTENDED_OK'), (1, ' verify', b'QT_PERSIST_READ_OK')]:
            guest = Guest(image, f'qt6_persist_{run}', work_disk=disk)
            try:
                guest.expect(b'xos64> ', timeout=30)
                send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=30)
                pump(guest, 1.5)
                before = resources(guest)
                out = command(guest, 'exec-file /bin/qtcore.elf' + arg, b'kind=exited code=', timeout=90)
                assert b'kind=exited code=0' in out and marker in out, out[-4000:]
                after = resources(guest)
                assert before == after, (before, after)
                command(guest, 'sync', b'[files] sync=ok')
                report['runs'].append({'run': run, 'marker': marker.decode(),
                                       'resources_before': before, 'resources_after': after,
                                       'qemu_command': guest.command})
            finally:
                a.report.with_name(a.report.stem + f'.{run}.serial.log').write_bytes(guest.output)
                guest.close()
        report['status'] = 'PASSED'
finally:
    a.report.write_text(json.dumps(report, indent=2) + '\n')
print(report['status'])
