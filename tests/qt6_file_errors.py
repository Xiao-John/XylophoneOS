# SPDX-License-Identifier: Apache-2.0
"""Qt file error paths on private FAT32 images with explicit fixture mutations."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
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
a = p.parse_args()
a.report.parent.mkdir(parents=True, exist_ok=True)
report = {'status':'FAILED', 'image_sha256':hashlib.sha256(a.image.read_bytes()).hexdigest(),
          'elf_sha256':hashlib.sha256(a.payload.read_bytes()).hexdigest(), 'runs':[]}

def alter(disk, mode):
    with disk.open('r+b') as f:
        boot = f.read(512)
        bps = struct.unpack_from('<H', boot, 11)[0]
        spc = boot[13]
        reserved = struct.unpack_from('<H', boot, 14)[0]
        fats = boot[16]
        fatsz = struct.unpack_from('<I', boot, 36)[0]
        total = struct.unpack_from('<I', boot, 32)[0]
        root = struct.unpack_from('<I', boot, 44)[0]
        data = reserved + fats * fatsz
        clusters = (total - data) // spc
        def cluster_offset(c): return (data + (c - 2) * spc) * bps
        def entry(cluster, name):
            f.seek(cluster_offset(cluster))
            block = f.read(spc * bps)
            for i in range(0, len(block), 32):
                if block[i:i+11] == name and block[i+11] != 0x0f:
                    return cluster_offset(cluster) + i, block[i:i+32]
            raise AssertionError('missing 8.3 fixture: ' + repr(name))
        _, bin_entry = entry(root, b'BIN        ')
        bin_cluster = struct.unpack_from('<H', bin_entry, 26)[0] | (struct.unpack_from('<H', bin_entry, 20)[0] << 16)
        if mode == 'readonly':
            pos, item = entry(bin_cluster, b'LOCK    TXT')
            f.seek(pos + 11); f.write(bytes([item[11] | 1]))
        else:
            # Preserve every allocated chain; mark only free entries allocated in
            # both FAT copies, and set FSInfo free count to zero. This synthetic
            # full disk is disposable and intentionally has orphan clusters.
            for fat in range(fats):
                f.seek((reserved + fat * fatsz) * bps)
                table = bytearray(f.read(fatsz * bps))
                for c in range(2, clusters + 2):
                    if struct.unpack_from('<I', table, c * 4)[0] & 0x0fffffff == 0:
                        struct.pack_into('<I', table, c * 4, 0x0fffffff)
                f.seek((reserved + fat * fatsz) * bps); f.write(table)
            for sector in (1, 7):
                f.seek(sector * bps + 488); f.write(struct.pack('<I', 0))
        f.flush()

try:
    with tempfile.TemporaryDirectory(prefix='xos_qt_file_errors_') as temp:
        tmp = Path(temp); image = tmp/'boot.img'; shutil.copyfile(a.image, image)
        empty = tmp/'empty'; empty.write_bytes(b'')
        locked = tmp/'locked'; locked.write_bytes(b'original')
        for mode, marker in [('readonly', b'QT_READONLY_ERROR_OK'), ('full', b'QT_FULL_ERROR_OK')]:
            disk = tmp/(mode+'.img'); create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/qtcore.elf', a.payload)
            transfer(disk, 'import', '/bin/LOCK.TXT', locked)
            transfer(disk, 'import', '/bin/FULL.TXT', empty)
            alter(disk, mode)
            guest = Guest(image, 'qt6_error_' + mode, work_disk=disk)
            try:
                guest.expect(b'xos64> ', timeout=30); send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=30); pump(guest, 1.5)
                before = resources(guest)
                out = command(guest, 'exec-file /bin/qtcore.elf ' + mode, b'kind=exited code=', timeout=90)
                assert b'kind=exited code=0' in out and marker in out, out[-4000:]
                after = resources(guest); assert before == after, (before, after)
                command(guest, 'sync', b'[files] sync=ok')
                report['runs'].append({'mode':mode, 'marker':marker.decode(), 'resources_before':before,
                                       'resources_after':after, 'qemu_command':guest.command})
            finally:
                a.report.with_name(a.report.stem+'.'+mode+'.serial.log').write_bytes(guest.output)
                guest.close()
            exported = tmp / (mode + '-check.bin')
            transfer(disk, 'export', '/bin/LOCK.TXT' if mode == 'readonly' else '/bin/FULL.TXT', exported)
            assert exported.read_bytes() == (b'original' if mode == 'readonly' else b'')
            report['runs'][-1]['content_preserved'] = True
        report['status']='PASSED'
finally:
    a.report.write_text(json.dumps(report, indent=2)+'\n')
print(report['status'])
