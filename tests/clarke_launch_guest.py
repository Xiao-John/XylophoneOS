#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observe real post-prepare start failure, abort results and retained denial."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def digest(path):
    with path.open('rb') as stream: return file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system','probe','output'):
        parser.add_argument('--'+name, required=True, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    manifest = json.loads((args.system/'manifest.json').read_bytes())
    selected = manifest['clarke_launch_probe']
    if (selected['loader_flag'] != 'XOS_LOADER_TEST_BAD_START_ENTRY=1' or selected['path'] != '/clarke_launch.elf' or
            selected['sha256'] != digest(args.probe) or selected['bytes'] != args.probe.stat().st_size):
        raise ValueError('launch fixture does not match the isolated system')
    required = ('src/user/loader/load.cpp','src/user/include/xos/execution.hpp',
                'src/shared/include/xos/net_service_abi.hpp','src/user/network/service_core.cpp',
                'src/user/include/xos/net_service_client.hpp','tests/fixtures/webkit/launch_probe.hpp')
    for name in required:
        if digest(ROOT/name) != manifest['sources'][name]: raise ValueError('qualified source changed: '+name)
    image = args.system/'xos-install.iso'
    if digest(image) != manifest['artifacts'][image.name]['sha256']: raise ValueError('system ISO differs from receipt')
    args.output.mkdir(parents=True, exist_ok=False)
    disk = args.output/'launch.img'; create_fat32(disk,512)
    transfer(disk,'import',selected['path'],args.probe)
    readback = args.output/'probe-readback.elf'; transfer(disk,'export',selected['path'],readback)
    if digest(readback) != selected['sha256']: raise ValueError('disk changed the launch probe')
    readback.unlink()
    report = {'status':'failed','system_manifest_sha256':digest(args.system/'manifest.json'),
              'iso_sha256':digest(image),'probe_sha256':selected['sha256'],
              'runner_sha256':digest(Path(__file__)),'sources':{name:manifest['sources'][name] for name in required},'cases':[]}
    guest = None
    try:
        guest = Guest(image,'clarke_launch',work_disk=disk,network=True,log_dir=args.output)
        guest.expect(b'xos64> ',timeout=30); send_bytes(guest,b'run\r'); guest.expect_supervisor(trace=True,timeout=30)
        command(guest,'demo quiet',b'demo tasks')
        if b'[net-start] pid=' in guest.output:
            command(guest,'net-stop',b'[wait] pid=',timeout=30)
        before = resources(guest); report['before_service'] = before
        output = command(guest,'net-start 41',b'[net-start] pid=',timeout=60)
        guest.expect(b'[net] ready native_v2=1',timeout=60)
        service = re.search(rb'\[net-start\] pid=(\d+)',output)
        if not service: raise AssertionError('no actual network service PID')
        report['service_pid'] = int(service[1])
        for number in range(20):
            output = command(guest,'clarke-start-test start',b'CLARKE_START_PROBE ',timeout=45)
            match = re.search(rb'CLARKE_START_PROBE double_abort=0 spawned=(-?\d+) pid=(\d+) first_abort=(-?\d+) '
                rb'never_started=(\d+) attempted=(\d+) abort=(-?\d+) release=(-?\d+) policy_before=(\d+) policy_after=(\d+) resources=(\d+) result=(PASS|FAIL)',output)
            if not match: raise AssertionError('missing complete start/abort outcome: '+repr(output))
            values = list(map(int,match.groups()[:-1])); report['cases'].append({'round':number,'fields':values,'result':match[11].decode()})
            if not (values[0] < 0 and values[1] > 0 and values[3:7] == [1,1,0,0] and
                    values[7:10] == [0,0,1] and match[11] == b'PASS'):
                raise AssertionError('actual start failure did not reclaim confirmed aborted child')
        output = command(guest,'clarke-start-test double-abort',b'CLARKE_START_PROBE ',timeout=45)
        match = re.search(rb'CLARKE_START_PROBE double_abort=1 spawned=(-?\d+) pid=(\d+) first_abort=(-?\d+) '
            rb'never_started=(\d+) attempted=(\d+) abort=(-?\d+) release=(-?\d+) policy_before=(\d+) policy_after=(\d+) resources=(\d+) result=(PASS|FAIL)',output)
        if not match: raise AssertionError('missing failed second-abort record')
        values = list(map(int,match.groups()[:-1])); report['cases'].append({'mode':'double_abort','fields':values,'result':match[11].decode()})
        if not (values[0] < 0 and values[1] > 0 and values[2] == 0 and values[3:5] == [1,1] and values[5] < 0 and
                values[6] == -6 and values[7:10] == [0,1,1] and match[11] == b'PASS'):
            raise AssertionError('unknown second abort must retain the denial')
        if b'CLARKE_LAUNCH_CHILD_RAN' in guest.output: raise AssertionError('a supposedly never-started child ran')
        command(guest,'net-stop',b'[wait] pid=',timeout=30)
        for _ in range(30):
            after = resources(guest)
            if after == before: break
            pump(guest,0.1)
        if after != before: raise AssertionError('network controller teardown did not restore resources')
        report.update(status='passed',after_service=after,never_started_marker_absent=True)
    finally:
        if guest:
            guest.close(); (args.output/'guest.serial.log').write_bytes(guest.output)
        disk.unlink(missing_ok=True)
        (args.output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        files={path.name:digest(path) for path in args.output.iterdir() if path.is_file() and path.name!='manifest.json'}
        (args.output/'manifest.json').write_text(json.dumps({'version':1,'files':files},indent=2,sort_keys=True)+'\n')
    print(report['status'])


if __name__ == '__main__': main()
