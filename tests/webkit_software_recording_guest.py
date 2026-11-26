#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the WebCore software recording and replay fixture in the XOS guest."""

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
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
    for name in ('system', 'target', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system_manifest = args.system / 'manifest.json'
    target_manifest = args.target / 'recording_link.json'
    system, target = (json.loads(path.read_bytes()) for path in (system_manifest, target_manifest))
    image = args.system / 'xos-install.iso'
    probe = args.target / 'software_recording.elf'
    fixture = root / 'tests/fixtures/webkit/software_recording.cpp'
    patch = root / 'src/ports/webkit/page/software_context.patch'
    iso_sha256 = digest(image)
    probe_sha256 = digest(probe)
    if (iso_sha256 != system['artifacts'][image.name]['sha256']
            or probe_sha256 != target['elf_sha256']
            or digest(fixture) != target['fixture_sha256']
            or digest(patch) != target['patch_sha256']):
        raise ValueError('Guest inputs differ from the build receipts')

    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'build_id': system['build_id'], 'iso_sha256': iso_sha256,
              'system_manifest_sha256': digest(system_manifest), 'target_manifest_sha256': digest(target_manifest),
              'probe_sha256': probe_sha256, 'runner_sha256': digest(Path(__file__))}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_webcore_recording_') as temporary:
            stage = Path(temporary)
            disk = stage / 'work.img'
            readback = stage / probe.name
            boot_path = '/recording.elf'
            create_fat32(disk, 512)
            transfer(disk, 'import', boot_path, probe)
            transfer(disk, 'export', boot_path, readback)
            report['fat_readback_sha256'] = digest(readback)
            if report['fat_readback_sha256'] != probe_sha256:
                raise ValueError('FAT changed the staged ELF')

            guest = Guest(image, 'webkit_software_recording', work_disk=disk, log_dir=args.output)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            report['resources_before'] = resources(guest)
            output = command(guest, 'exec-file ' + boot_path, b'[wait] pid=', timeout=90)
            report['resources_after'] = resources(guest)
            marker = b'XOS_WEBCORE_SOFTWARE_RECORDING_PASS 16x8 red black blue white'
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', output)
            report['exit_codes'] = [int(code) for code in exits]
            report['marker_count'] = len(re.findall(re.escape(marker) + rb'\r?\n', output))
            if (exits != [b'0'] or report['marker_count'] != 1
                    or report['resources_after'] != report['resources_before']):
                raise AssertionError(f'Unexpected recording result: {output[-1500:]!r}')
            report['marker'] = marker.decode()
            report['status'] = 'passed_subset'
    finally:
        if guest:
            guest.close()
            (args.output / 'guest.serial.log').write_bytes(guest.output)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
