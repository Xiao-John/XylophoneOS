#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Recheck target-only discovery and the WebCore LibXml2 API in XOS."""

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
    system_manifest = args.system / 'manifest.json'
    target_manifest = args.target / 'manifest.json'
    system = json.loads(system_manifest.read_bytes())
    target = json.loads(target_manifest.read_bytes())
    if digest(image) != system['artifacts'][image.name]['sha256']:
        raise ValueError('System ISO differs from its build receipt')
    if target['status'] != 'target_libxml2_linked':
        raise ValueError('Target LibXml2 receipt is incomplete')
    for name, expected in target['artifacts'].items():
        if digest(args.target / name) != expected:
            raise ValueError(f'Unexpected LibXml2 artifact bytes: {name}')

    report = {'status': 'failed', 'build_id': system['build_id'], 'iso_sha256': digest(image),
              'system_manifest_sha256': digest(system_manifest), 'target_manifest_sha256': digest(target_manifest),
              'runner_sha256': digest(Path(__file__))}
    guest = None
    try:
        fixture = root / 'tests/fixtures/webkit/xml_package'
        cmake = args.output / 'cmake'
        with (args.output / 'discovery.log').open('w') as log:
            subprocess.run(['cmake', '-S', fixture, '-B', cmake,
                            f'-DXOS_XML_PREFIX={args.target / "prefix"}'],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        report['discovery'] = {'version': (cmake / 'target-version.txt').read_text().strip(),
                               'fixture_sha256': digest(fixture / 'CMakeLists.txt')}
        with tempfile.TemporaryDirectory(prefix='xos_webkit_xml_') as temporary:
            disk = Path(temporary) / 'work.img'
            readback = Path(temporary) / 'readback.elf'
            create_fat32(disk, 512)
            transfer(disk, 'import', '/xml_push.elf', args.target / 'xml_push.elf')
            transfer(disk, 'export', '/xml_push.elf', readback)
            report['guest_probe_sha256'] = digest(readback)
            if report['guest_probe_sha256'] != target['artifacts']['xml_push.elf']:
                raise ValueError('FAT bytes differ from the target ELF')
            guest = Guest(image, 'webkit_xml', work_disk=disk, log_dir=args.output)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            report['resources_before'] = resources(guest)
            cases = (('valid', '', b'WEBKIT_XML_PUSH_PASS starts=2 ends=2 utf8_bytes=10', 0),
                     ('malformed', ' malformed', b'WEBKIT_XML_PUSH_REJECTED mismatched_close', 2))
            for name, arg, marker, expected in cases:
                out = command(guest, 'exec-file /xml_push.elf' + arg, b'[wait] pid=', timeout=90)
                outcomes = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', out)
                after = resources(guest)
                if out.count(marker) != 1 or outcomes != [str(expected).encode()] or after != report['resources_before']:
                    raise AssertionError(f'XML outcome or resources differed for {name}: {out[-2000:]!r}')
                report[name] = {'exit_code': expected, 'resources_after': after}
            report['status'] = 'passed_subset'
    finally:
        if guest:
            guest.close()
            (args.output / 'guest.serial.log').write_bytes(guest.output)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
