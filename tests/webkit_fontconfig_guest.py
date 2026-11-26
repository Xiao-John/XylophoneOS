#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Replay native Fontconfig and Skia font selection on the XOS guest."""

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
    for name in ('target', 'font-target', 'system', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    args = parser.parse_args()
    system_receipt = args.system / 'manifest.json'
    target_receipt = args.target / 'manifest.json'
    font_receipt = args.font_target / 'manifest.json'
    system, target, font = (json.loads(path.read_bytes()) for path in
                            (system_receipt, target_receipt, font_receipt))
    image = args.system / 'xos-install.iso'
    skia = target['status'] == 'target_skia_fontconfig_linked'
    executable = args.target / ('skia_fontconfig.elf' if skia else 'fontconfig_match.elf')
    sample = args.font_target / 'sample.ttf'
    if ((not skia and target['status'] != 'target_fontconfig_linked')
        or digest(image) != system['artifacts'][image.name]['sha256']
        or digest(executable) != target['artifacts'][executable.name]
        or digest(font_receipt) != target['font_target_manifest_sha256']
        or digest(sample) != font['artifacts'][sample.name]):
        raise ValueError('Guest input differs from its upstream build receipt')

    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'target': target['status'],
              'build_id': system['build_id'], 'iso_sha256': digest(image),
              'system_manifest_sha256': digest(system_receipt), 'target_manifest_sha256': digest(target_receipt),
              'probe_sha256': digest(executable), 'font_sha256': digest(sample),
              'fixture_sha256': target['fixture_sha256'], 'runner_sha256': digest(Path(__file__)), 'cases': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_fontconfig_') as temporary:
            stage = Path(temporary)
            disk = stage / 'work.img'
            create_fat32(disk, 512)
            for name in ('/fc-fonts', '/fc-empty'):
                transfer(disk, 'mkdir', name)
            font_path = '/fc-fonts/dejavu.ttf'
            for path, local in (('/fontmatch.elf', executable), (font_path, sample)):
                readback = stage / Path(path).name
                transfer(disk, 'import', path, local)
                transfer(disk, 'export', path, readback)
                if digest(readback) != digest(local):
                    raise ValueError(f'FAT changed the staged input: {path}')

            guest = Guest(image, 'webkit_fontconfig', work_disk=disk, log_dir=args.output)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report['resources_before'] = baseline
            if skia:
                cases = (('/fc-fonts', 0, rb'XOS_SKIA_FONTCONFIG_PASS family=DejaVu_Sans glyph=[1-9][0-9]* ink=[1-9][0-9]*'),
                         ('/fc-empty', 5, rb'XOS_SKIA_FONTCONFIG_EMPTY'))
            else:
                cases = (('/fc-fonts', 0, rb'XOS_FONTCONFIG_MATCH_PASS family=DejaVu_Sans alias=sans-serif glyph=03bb'),
                         ('/fc-empty', 5, rb'XOS_FONTCONFIG_DIRECTORY_EMPTY'))
            for directory, code, marker in cases:
                invocation = f'exec-file /fontmatch.elf {directory}'
                if not skia:
                    invocation += ' ' + font_path
                output = command(guest, invocation, b'[wait] pid=', timeout=90)
                exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', output)
                markers = re.findall(marker + rb'\r?\n', output)
                after = resources(guest)
                report['cases'].append({'directory': directory, 'exits': [int(exit) for exit in exits],
                                        'marker_count': len(markers),
                                        'markers': [line.decode().strip() for line in markers],
                                        'resources_after': after})
                if exits != [str(code).encode()] or len(markers) != 1 or after != baseline:
                    raise AssertionError(f'Unexpected Fontconfig result: {output[-1500:]!r}')
            report['status'] = 'passed_subset'
    finally:
        if guest:
            guest.close()
            (args.output / 'guest.serial.log').write_bytes(guest.output)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
