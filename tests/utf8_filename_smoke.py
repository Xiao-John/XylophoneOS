# SPDX-License-Identifier: Apache-2.0
"""Exercise UTF-8 filenames on a private work disk and after guest reboot."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--sdk', type=Path, required=True)
    a = p.parse_args()
    report = {'status': 'failed', 'checks': []}
    try:
        with tempfile.TemporaryDirectory(prefix='xos_utf8_name_') as temp:
            disk = Path(temp) / 'disk.img'
            exe = Path(temp) / 'name_probe'
            cc = shutil.which('x86_64-elf-g++')
            if not cc: raise RuntimeError('cross compiler missing')
            libgcc = subprocess.check_output([cc, '-print-libgcc-file-name'], text=True).strip()
            sdk = a.sdk
            subprocess.run([cc, '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
                '-isystem', str(sdk / 'include'), '-nostdlib', '-static', '-no-pie',
                '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T', str(sdk / 'user.ld'),
                str(sdk / 'crt0_posix.o'), str(ROOT / 'tests/fixtures/utf8_names/libc_probe.cpp'),
                '-Wl,--start-group', str(sdk / 'lib/libxos.a'), str(sdk / 'lib/libxos_loader.a'),
                str(sdk / 'lib/libc.a'), str(sdk / 'lib/libm.a'), libgcc, '-Wl,--end-group', '-o', str(exe)], check=True)
            create_fat32(disk, 512)
            transfer(disk, 'import', '/probe', exe)
            def boot():
                guest = Guest(a.image, 'utf8_filename', work_disk=disk)
                guest.expect(b'xos64> ', timeout=30)
                start = len(guest.output); send_bytes(guest, b'run\r')
                guest.expect_supervisor(start=start, timeout=40)
                pump(guest, .4); send_bytes(guest, b'demo quiet\r'); pump(guest, .4)
                return guest
            def command(guest, command, expect=b'xsh> '):
                start = len(guest.output); send_bytes(guest, command.encode('utf-8') + b'\r')
                guest.expect(expect, start=start, timeout=30)
                return bytes(guest.output[start:])
            guest = boot()
            try:
                command(guest, 'mkdir 中文')
                command(guest, 'edit 中文/你好.txt', b'| ')
                command(guest, 'hello', b'| ')
                command(guest, ':wq')
                assert b'hello' in command(guest, 'cat 中文/你好.txt')
                assert '你好.txt'.encode() in command(guest, 'ls 中文')
                command(guest, 'mv 中文/你好.txt 中文/世界.txt')
                assert b'hello' in command(guest, 'cat 中文/世界.txt')
                command(guest, 'sync')
                assert b'UTF8_LIBC_OK' in command(guest, '/probe')
                report['checks'].append('libc_create_list_rename_read_invalid_unlink')
                report['checks'].append('mkdir_create_list_read_rename_sync')
            finally:
                guest.close()
            guest = boot()
            try:
                assert b'hello' in command(guest, 'cat 中文/世界.txt')
                assert '世界.txt'.encode() in command(guest, 'ls 中文')
                command(guest, 'rm 中文/世界.txt')
                assert '世界.txt'.encode() not in command(guest, 'ls 中文')
                report['checks'].append('reboot_read_list_remove')
            finally:
                guest.close()
        report['status'] = 'passed'
    finally:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
