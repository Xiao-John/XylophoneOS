#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the ordinary COW parent-exit probe with a source-bound system image."""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from dash_b2_smoke import build_probe
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    system = args.system.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((system / 'manifest.json').read_text())
    for path, expected in manifest['sources'].items():
        if sha(ROOT / path) != expected:
            raise ValueError('source changed since system build: ' + path)
    for path, item in manifest['artifacts'].items():
        if sha(system / path) != item['sha256']:
            raise ValueError('system artifact changed since build: ' + path)
    source = ROOT / 'tests/fixtures/cow2_runtime_probe.c'
    binary = out / 'cow2.elf'
    build_probe(source, binary, system / 'sdk')
    report = {'status': 'failed', 'build_id': manifest['build_id'],
              'image_sha256': sha(system / 'xos-install.iso'),
              'source_sha256': sha(source), 'elf_sha256': sha(binary), 'checks': []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_cow2_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/cow2.elf', binary)
            guest = Guest(system / 'xos-install.iso', 'cow2_runtime', work_disk=disk, iso=True)
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            pump(guest, .2)
            baseline = resources(guest)
            output = command(guest, 'exec-driver /bin/cow2.elf', b'kind=exited code=', timeout=180)
            if b'[cow2-runtime] parent_exit_child_write=PASS' not in output or b'kind=exited code=0' not in output:
                raise AssertionError(output[-4000:])
            if resources(guest) != baseline:
                raise AssertionError('resources drifted after COW probe')
            report['checks'] = ['parent_exit_child_write', 'resources_restored']
            report['status'] = 'passed'
    finally:
        if guest:
            (out / 'guest.serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS ordinary COW parent-exit guest')


if __name__ == '__main__':
    main()
