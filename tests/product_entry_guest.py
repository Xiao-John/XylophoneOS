#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check canonical and legacy product paths through the real session parent."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import pump, send_bytes
from work_disk import transfer

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run_case(args, child, paths, desktop, browser):
    name = 'canonical' if desktop == 'mobius' else 'legacy'
    with tempfile.TemporaryDirectory(prefix='xos_product_entries_') as temp:
        disk = Path(temp) / 'work.img'
        create_fat32(disk, 512)
        transfer(disk, 'mkdir', '/bin')
        for path in paths:
            transfer(disk, 'import', f'/bin/{path}.elf', child)
        transfer(disk, 'import', '/bin/session.elf', args.session)
        guest = Guest(args.image.resolve(), str(args.output.relative_to(ROOT / 'build') / name),
                      work_disk=disk, iso=True)
        try:
            guest.expect(b'xos64> ', timeout=45)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=45)
            pump(guest, 1.5)
            baseline = resources(guest)
            start = len(guest.output)
            send_bytes(guest, b'exec-driver /bin/session.elf\r')
            guest.expect(b'DESKTOP_RESUMED Application closed.', start=start, timeout=45)
            guest.expect_supervisor(start=start, timeout=45)
            serial = bytes(guest.output)[start:]
            assert serial.count(f'DESKTOP_ENTRY /bin/{desktop}.elf'.encode()) == 2, serial
            assert serial.count(f'BROWSER_ENTRY /bin/{browser}.elf'.encode()) == 1, serial
            assert b'kind=exited code=0' in serial and resources(guest) == baseline
            return {'case': name, 'desktop': desktop, 'browser': browser, 'resources': baseline}
        finally:
            guest.close()
            (args.output / f'{name}.serial.log').write_bytes(guest.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('image', 'sdk', 'session', 'output'):
        parser.add_argument('--' + key, required=True, type=Path)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt_path = args.session.with_suffix('.receipt.json')
    receipt = json.loads(receipt_path.read_text())
    assert digest(args.session) == receipt['elf_sha256']
    for name, expected in receipt['inputs'].items():
        assert digest(Path(name)) == expected, name

    fixture = ROOT / 'tests/fixtures/product_entries/session_child.cpp'
    child = args.output / 'child.elf'
    subprocess.run([sys.executable, str(args.sdk.resolve() / 'compile.py'),
                    str(fixture), '-o', str(child)], check=True)
    checks = [
        run_case(args, child, ('mobius', 'desktop', 'clarke', 'browser'), 'mobius', 'clarke'),
        run_case(args, child, ('desktop', 'browser'), 'desktop', 'browser'),
    ]
    report = {'status': 'passed', 'checks': checks, 'image_sha256': digest(args.image),
              'session_sha256': digest(args.session), 'receipt_sha256': digest(receipt_path),
              'fixture_sha256': digest(fixture), 'child_sha256': digest(child),
              'sdk_manifest_sha256': digest(args.sdk / 'manifest.json')}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
