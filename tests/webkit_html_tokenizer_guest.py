#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the locked WebCore tokenizer against an HTML file read from the XOS FAT volume."""

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
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    image = args.system / 'xos-install.iso'
    system_receipt = args.system / 'manifest.json'
    target_receipt = args.target / 'manifest.json'
    system = json.loads(system_receipt.read_bytes())
    target = json.loads(target_receipt.read_bytes())
    sample = root / 'tests/fixtures/webkit/html_tokenizer/page.html'
    if digest(image) != system['artifacts'][image.name]['sha256']:
        raise ValueError('System ISO differs from its build receipt')
    if target['status'] != 'target_webcore_html_tokenizer_linked' or digest(sample) != target['sample_sha256']:
        raise ValueError('The tokenizer probe or HTML input is unbound')
    for name, expected in target['artifacts'].items():
        if digest(args.target / name) != expected:
            raise ValueError(f'Tokenizer artifact differs from its receipt: {name}')

    report = {'status': 'failed', 'build_id': system['build_id'], 'iso_sha256': digest(image),
              'system_manifest_sha256': digest(system_receipt), 'target_manifest_sha256': digest(target_receipt),
              'runner_sha256': digest(Path(__file__))}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_webcore_tokenizer_') as temporary:
            folder = Path(temporary)
            disk = folder / 'work.img'
            create_fat32(disk, 512)
            files = (('html_slice.elf', args.target / 'html_slice.elf', target['artifacts']['html_slice.elf']),
                     ('page.html', sample, target['sample_sha256']))
            report['fat_readback_sha256'] = {}
            for name, original, expected in files:
                transfer(disk, 'import', '/' + name, original)
                readback = folder / name
                transfer(disk, 'export', '/' + name, readback)
                report['fat_readback_sha256'][name] = digest(readback)
                if report['fat_readback_sha256'][name] != expected:
                    raise ValueError(f'FAT staging altered {name}')
            guest = Guest(image, 'webkit_html_tokenizer', work_disk=disk, log_dir=args.output)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            report['resources_before'] = resources(guest)
            cases = (('missing', '/missing.html', b'WEBKIT_HTML_INPUT_MISSING', 2),
                     ('valid', '/page.html', b'WEBKIT_HTML_TOKENIZER_PASS doctype=html tag=p '
                      b'attribute=data-k text_chars=4 eof=1', 0))
            for name, path, marker, exit_code in cases:
                out = command(guest, 'exec-file /html_slice.elf ' + path, b'[wait] pid=', timeout=120)
                status = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', out)
                after = resources(guest)
                if status != [str(exit_code).encode()] or out.count(marker) != 1 or after != report['resources_before']:
                    raise AssertionError(f'Unexpected tokenizer output or resources for {name}: {out[-2000:]!r}')
                report[name] = {'exit_code': exit_code, 'resources_after': after}
            report['status'] = 'passed_subset'
    finally:
        if guest:
            guest.close()
            (args.output / 'guest.serial.log').write_bytes(guest.output)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
