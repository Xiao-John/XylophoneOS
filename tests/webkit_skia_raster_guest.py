#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the locked Skia CPU drawing path in the XOS guest."""

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
    for name in ('target', 'system', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--font-target', type=lambda value: Path(value).resolve(),
                        help='also exercise the positioned stream and FAT font with the locked font build')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    image = args.system / 'xos-install.iso'
    system_receipt = args.system / 'manifest.json'
    target_receipt = args.target / 'manifest.json'
    system = json.loads(system_receipt.read_bytes())
    target = json.loads(target_receipt.read_bytes())
    if digest(image) != system['artifacts'][image.name]['sha256']:
        raise ValueError('System ISO differs from its build receipt')
    if target['status'] != 'target_skia_raster_linked':
        raise ValueError('The target Skia raster receipt is incomplete')
    for name, expected in target['artifacts'].items():
        artifact = (args.target / name).resolve()
        if not artifact.is_relative_to(args.target) or digest(artifact) != expected:
            raise ValueError(f'Raster artifact differs from its receipt: {name}')

    filename = 'cmake/skia_raster_probe'
    if args.font_target:
        font_manifest = args.font_target / 'manifest.json'
        font_input = args.font_target / 'sample.ttf'
        font_hash = json.loads(font_manifest.read_bytes())['artifacts']['sample.ttf']
        if (digest(font_manifest) != target['freetype_target_manifest_sha256']
                or digest(font_input) != font_hash):
            raise ValueError('Font input differs from the bound font build')
        stream_filename = 'cmake/skia_file_stream_probe'
        stream_hash = target['artifacts'][stream_filename]
    report = {'status': 'failed', 'build_id': system['build_id'], 'iso_sha256': digest(image),
              'system_manifest_sha256': digest(system_receipt), 'target_manifest_sha256': digest(target_receipt),
              'runner_sha256': digest(Path(__file__))}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_webkit_raster_') as temporary:
            directory = Path(temporary)
            disk = directory / 'work.img'
            readback = directory / 'raster.elf'
            create_fat32(disk, 512)
            transfer(disk, 'import', '/raster.elf', args.target / filename)
            transfer(disk, 'export', '/raster.elf', readback)
            report['guest_probe_sha256'] = digest(readback)
            if report['guest_probe_sha256'] != target['artifacts'][filename]:
                raise ValueError('FAT staging altered the target Skia ELF')
            if args.font_target:
                for guest_path, artifact, expected in (('/stream.elf', args.target / stream_filename, stream_hash),
                                                        ('/dejavu.ttf', font_input, font_hash)):
                    staged = directory / Path(guest_path).name
                    transfer(disk, 'import', guest_path, artifact)
                    transfer(disk, 'export', guest_path, staged)
                    if digest(staged) != expected:
                        raise ValueError(f'FAT stage changed {guest_path}')
                report['file_stream'] = {'probe_sha256': stream_hash, 'font_sha256': font_hash, 'checks': []}
            guest = Guest(image, 'webkit_skia_raster', work_disk=disk, log_dir=args.output)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            report['resources_before'] = resources(guest)
            output = command(guest, 'exec-file /raster.elf', b'[wait] pid=', timeout=90)
            marker = b'WEBKIT_SKIA_RASTER_PASS 12x10 background=white clipped=blue overlap=red'
            exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', output)
            report['resources_after'] = resources(guest)
            if output.count(marker) != 1 or exits != [b'0'] or report['resources_before'] != report['resources_after']:
                raise AssertionError(f'Unexpected Skia output, exit or resource use: {output[-2000:]!r}')
            if args.font_target:
                stream_marker = b'XOS_SKIA_FILE_STREAM_PASS full=8192 tail=17 eof=0 offsets=preserved overflow=checked'
                text_marker = b'XOS_SKIA_FAT_FONT_PASS glyphs=59,50,54 ink=275'
                cases = (('/dejavu.ttf', 0, (stream_marker, text_marker)),
                         ('/missing.ttf', 3, (b'XOS_SKIA_FAT_FONT_UNAVAILABLE',)))
                for path, code, markers in cases:
                    output = command(guest, 'exec-file /stream.elf ' + path, b'[wait] pid=', timeout=90)
                    exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', output)
                    after = resources(guest)
                    if (any(output.count(marker) != 1 for marker in markers)
                            or exits != [str(code).encode()] or after != report['resources_before']):
                        raise AssertionError(f'Unexpected Skia file output, exit or resource use: {output[-2000:]!r}')
                    report['file_stream']['checks'].append({'path': path, 'exit_code': code,
                                                            'markers': [marker.decode() for marker in markers],
                                                            'resources_after': after})
            report['status'] = 'passed_subset'
            report['sample'] = {'width': 12, 'height': 10, 'background': 'white', 'clipped': 'blue', 'overlap': 'red'}
    finally:
        if guest:
            guest.close()
            (args.output / 'guest.serial.log').write_bytes(guest.output)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
