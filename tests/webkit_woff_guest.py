#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the locked WebCore WOFF converter in an ordinary XOS guest."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'elf', 'receipt', 'sdk-kit', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_bytes())
    port = ROOT / 'src/ports/webkit/page'
    inputs = {
        'elf_sha256': digest(args.elf),
        'fixture_sha256': digest(ROOT / 'tests/fixtures/webkit/woff_target.cpp'),
        'source_lock_sha256': digest(port / 'source_lock.json'),
        'patch_sha256': digest(port / 'font_and_bitstream_formats.patch'),
        'sdk_manifest_sha256': digest(args.sdk_kit / 'sdk/manifest.json'),
        'sdk_profile_sha256': digest(args.sdk_kit / 'profile.json'),
    }
    if any(receipt[key] != value for key, value in inputs.items()):
        raise ValueError('WOFF artifact differs from its link receipt')
    manifest = args.system / 'manifest.json'
    build = json.loads(manifest.read_bytes())
    image = args.system / 'xos-install.iso'
    image_sha = digest(image)
    if image_sha != build['artifacts'][image.name]['sha256']:
        raise ValueError('ordinary ISO differs from its build manifest')

    args.output.mkdir(parents=True, exist_ok=False)
    record = {'status': 'failed', **inputs, 'iso_sha256': image_sha,
              'build_id': build['build_id'], 'system_manifest_sha256': digest(manifest),
              'link_receipt_sha256': digest(args.receipt), 'runner_sha256': digest(Path(__file__))}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_webcore_woff_') as directory:
            work = Path(directory)
            disk = work / 'disk.img'
            create_fat32(disk, 512)
            transfer(disk, 'import', '/woff.elf', args.elf)
            transfer(disk, 'export', '/woff.elf', work / 'readback.elf')
            record['fat_readback_sha256'] = digest(work / 'readback.elf')
            if record['fat_readback_sha256'] != inputs['elf_sha256']:
                raise ValueError('the copied WOFF ELF differs from the linked ELF')
            guest = Guest(image, 'webkit_woff', work_disk=disk, log_dir=args.output)
            record['qemu_version'] = subprocess.check_output(
                [guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            command(guest, 'demo quiet', b'demo tasks')
            record['resources_before'] = resources(guest)
            observed = command(guest, 'exec-file /woff.elf', b'[wait] pid=', timeout=60)
            record['observed_output'] = observed.decode()
            record['resources_after'] = resources(guest)
            marker = b'XOS_WEBCORE_WOFF_OK uncompressed deflate truncated'
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', observed)
            if observed.count(marker) != 1 or exits != [b'0'] or record['resources_before'] != record['resources_after']:
                raise AssertionError('WOFF conversion or resource recovery differed')
            record['status'] = 'passed_subset'
    finally:
        if guest:
            guest.close()
            serial = args.output / 'webkit_woff_serial.log'
            record['serial_sha256'] = digest(serial)
        (args.output / 'report.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(record['status'])


if __name__ == '__main__':
    main()
