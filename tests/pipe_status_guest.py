#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run live, non-consuming, owner-scoped pipe status on the actual XOS kernel."""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_pipe_status_probe import INPUTS
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
from xos_app import tree_receipt
from xypm_format import sha_file

CASES = ['empty_direction', 'non_consuming', 'capacity', 'invalid_output_and_console',
         'reserved_rejected', 'foreign_owner_denied', 'eof', 'stale_no_output', 'broken_writer']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system, fixture, out = (path.resolve() for path in (args.system, args.fixture, args.output))
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((system / 'manifest.json').read_bytes())
    receipt = json.loads((fixture / 'receipt.json').read_bytes())
    report = {'status': 'failed', 'checks': [], 'system_build_id': manifest['build_id'],
              'iso_sha256': sha_file(system / 'xos-install.iso'), 'elf_sha256': receipt['elf_sha256'],
              'sdk_tree_sha256': receipt['sdk_tree_sha256']}
    guest = None

    def verify():
        assert all(sha_file(ROOT / path) == digest for path, digest in manifest['sources'].items())
        assert all(sha_file(system / path) == value['sha256'] for path, value in manifest['artifacts'].items())
        assert receipt['sources'] == {path: sha_file(ROOT / path) for path in INPUTS}
        assert tree_receipt(system / 'sdk')[0] == receipt['sdk_tree_sha256']
        assert sha_file(fixture / 'pipe_status.elf') == receipt['elf_sha256']

    try:
        verify()
        with tempfile.TemporaryDirectory() as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/pipe_status.elf', fixture / 'pipe_status.elf')
            guest = Guest(system / 'xos-install.iso', 'pipe_status', iso=True, work_disk=disk,
                          qmp_enabled=False, log_dir=out)
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r'); guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            baseline = resources(guest)
            report['baseline'] = baseline
            for number in range(3):
                output = command(guest, 'exec-driver /bin/pipe_status.elf', b'kind=exited code=', timeout=60)
                assert b'PIPE_STATUS_FAIL' not in output and b'PIPE_STATUS_OK cases=9' in output, output[-4000:]
                assert re.findall(rb'PIPE_STATUS_PASS ([a-z_]+)', output) == [name.encode() for name in CASES]
                assert b'kind=exited code=0' in output and resources(guest) == baseline
                report['checks'].append({'round': number, 'cases': CASES, 'status': 'passed'})
            guest.close(); guest = None
        verify()
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest: guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
