#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the isolated COW1 page-table probe and the ordinary eager build."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from boot_smoke import Guest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    system = args.system.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((system / 'manifest.json').read_text())
    assert manifest['cow1_probe'] is args.probe
    assert not args.probe or manifest['vm1_probe']
    for path, digest in manifest['sources'].items():
        assert sha(ROOT / path) == digest, path
    for path, details in manifest['artifacts'].items():
        assert sha(system / path) == details['sha256'], path
    report = {'status': 'failed', 'build_id': manifest['build_id'],
              'image_sha256': sha(system / 'xos-install.iso'), 'checks': []}
    guest = None
    try:
        guest = Guest(system / 'xos-install.iso', str(out.relative_to(ROOT / 'build')) + '/guest', iso=True)
        report['qemu_command'] = guest.command
        guest.expect(b'xos64> ', timeout=60)
        assert b'[vm] event=self_check result=pass' in guest.output
        if args.probe:
            assert b'[cow1-probe] page_tables=pass' in guest.output
            assert b'[cow1-probe] page_tables=fail' not in guest.output
            report['checks'].append('isolated_page_table_self_check')
        else:
            assert b'[cow1-probe]' not in guest.output
            report['checks'].append('ordinary_image_does_not_enable_cow1_probe')
        report['status'] = 'passed'
    finally:
        if guest:
            (out / 'guest.serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS COW1 page-table probe' if args.probe else 'PASS eager image isolation')


if __name__ == '__main__':
    main()
