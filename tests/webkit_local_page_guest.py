#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check DOM, CSS geometry and rendered pixels using a full WebCore page in XOS."""

import argparse
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
from webkit_software_recording_guest import digest
from work_disk import transfer

FIXTURES = ROOT / 'tests/fixtures/webkit'
MARKER = b'XOS_WEBCORE_LOCAL_PAGE_PASS 120x90 DOM CSS red blue white'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('system', 'target', 'sdk-kit', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    args = parser.parse_args()

    system_path = args.system / 'manifest.json'
    target_path = args.target / 'local_page_link.json'
    system = json.loads(system_path.read_bytes())
    target = json.loads(target_path.read_bytes())
    image = args.system / 'xos-install.iso'
    probe = args.target / 'local_page.elf'
    html = FIXTURES / 'local_page.html'
    port = ROOT / 'src/ports/webkit'
    inputs = {
        'elf_sha256': digest(probe),
        'fixture_sha256': digest(FIXTURES / 'local_page.cpp'),
        'html_sha256': digest(html),
        'sdk_manifest_sha256': digest(args.sdk_kit / 'sdk/manifest.json'),
        'sdk_profile_sha256': digest(args.sdk_kit / 'profile.json'),
        'source_lock_sha256': digest(port / 'source_lock.json'),
        'software_context_sha256': digest(port / 'page/software_context.patch'),
        'software_buffers_sha256': digest(port / 'page/software_buffers.patch'),
        'software_graph_sha256': digest(port / 'page/software_graph.patch'),
    }
    if any(target[key] != value for key, value in inputs.items()):
        raise ValueError('Local page inputs differ from the link receipt')
    iso_sha256 = digest(image)
    if iso_sha256 != system['artifacts'][image.name]['sha256']:
        raise ValueError('System ISO differs from its build manifest')

    data = html.read_bytes()
    old = b'background: blue;'
    if data.count(old) != 1:
        raise ValueError('Expected one CSS rule for the negative paint check')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {
        'status': 'failed',
        'build_id': system['build_id'],
        'iso_sha256': iso_sha256,
        'system_manifest_sha256': digest(system_path),
        'target_manifest_sha256': digest(target_path),
        'runner_sha256': digest(Path(__file__)),
        'inputs': inputs,
        'checks': [],
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_webcore_page_') as temporary:
            work = Path(temporary)
            disk = work / 'page.img'
            bad = work / 'wrong.html'
            bad.write_bytes(data.replace(old, b'background: yellow;'))
            create_fat32(disk, 512)
            readback_hashes = {}
            for path, local in (('/page.elf', probe), ('/page.html', html), ('/wrong.html', bad)):
                readback = work / (Path(path).name + '.readback')
                transfer(disk, 'import', path, local)
                transfer(disk, 'export', path, readback)
                readback_hashes[path] = digest(readback)
                if readback_hashes[path] != digest(local):
                    raise ValueError(f'FAT changed {path}')
            report['fat_readback_sha256'] = readback_hashes

            guest = Guest(image, 'webkit_local_page', work_disk=disk, log_dir=args.output)
            report['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=30)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report['resources_before'] = baseline

            for fixture, expected_exit, expected_markers in (('/page.html', 0, 1), ('/wrong.html', 11, 0)):
                output = command(guest, f'exec-file /page.elf {fixture}', b'[wait] pid=', timeout=120)
                exits = [int(code) for code in re.findall(rb'\[wait\] pid=\d+ kind=exited code=(\d+)', output)]
                markers = len(re.findall(re.escape(MARKER) + rb'\r?\n', output))
                after = resources(guest)
                report['checks'].append({
                    'fixture': fixture, 'exit_codes': exits, 'marker_count': markers, 'resources_after': after,
                })
                if exits != [expected_exit] or markers != expected_markers or after != baseline:
                    raise AssertionError(f'Unexpected WebCore page result: {output[-1600:]!r}')

            report['status'] = 'passed_subset'
    finally:
        if guest:
            guest.close()
            (args.output / 'guest.serial.log').write_bytes(guest.output)
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
