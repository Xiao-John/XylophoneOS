# SPDX-License-Identifier: Apache-2.0
"""Target PR #3 integration: display must not intercept entropy or wall time."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from cpython_py3_b2_smoke import install_stage
from make_work_disk import create_fat32
from process_smoke import command, resources
from stage_cpython import stage_cpython
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--python-work', type=Path, required=True)
    args = parser.parse_args()
    system = args.system.resolve(strict=True)
    out = system.parent
    manifest = json.loads((system / 'manifest.json').read_text())
    stage, stage_manifest = stage_cpython(args.python_work.resolve(strict=True), phase='PY3')
    report = {'status': 'failed', 'build_id': manifest['build_id'],
              'image_sha256': sha(system / 'xos.img'),
              'python_sha256': sha(args.python_work / 'target_build/python.exe'),
              'python_fingerprint': stage_manifest['fingerprint'], 'checks': []}
    guest = None
    prefix = out.relative_to(ROOT / 'build').as_posix()
    def mark(name):
        report['checks'].append(name)
    def python_probe():
        before = time.time_ns()
        output = command(guest, 'python3 /work/integration.py', b'kind=exited code=', timeout=120)
        after = time.time_ns()
        match = re.search(rb'PR3_ENTROPY_CLOCK_OK wall_ns=(\d+)', output)
        assert match and b'kind=exited code=0' in output, output[-1800:]
        assert before - 30_000_000_000 <= int(match[1]) <= after + 30_000_000_000
    try:
        for name, digest in manifest['sources'].items():
            assert sha(ROOT / name) == digest, name
        for name, info in manifest['artifacts'].items():
            assert sha(system / name) == info['sha256'], name
        numbers = {}
        for path in (ROOT / 'src/shared/include/xos').glob('*abi.hpp'):
            for name, value in re.findall(r'\b(sys_[a-z0-9_]+)\s*=\s*(\d+)', path.read_text()):
                assert int(value) not in numbers, (name, value, numbers.get(int(value)))
                numbers[int(value)] = name
        assert {k: numbers[k] for k in (63, 64, 65, 66)} == {
            63: 'sys_random_bytes', 64: 'sys_clock_realtime',
            65: 'sys_display', 66: 'sys_display_present'}
        sdk = json.loads((system / 'sdk/manifest.json').read_text())
        assert sdk['display_extensions']['syscalls'] == [65, 66]
        assert sdk['runtime_model'] == 'single' and 'configuration' in sdk
        mark('source_artifact_sdk_binding_and_distinct_syscall_numbers')
        with tempfile.TemporaryDirectory(prefix='xos_pr3_compat_') as folder:
            folder = Path(folder)
            disk = folder / 'work.img'
            create_fat32(disk, 2048)
            install_stage(disk, stage)
            transfer(disk, 'mkdir', '/work')
            script = folder / 'integration.py'
            script.write_text('''import os, time
from datetime import datetime, timezone
assert len(os.urandom(512)) == 512
wall = time.time_ns()
assert abs(datetime.now(timezone.utc).timestamp()*1e9 - wall) < 2e9
before = time.monotonic_ns()
time.sleep(0.04)
assert time.monotonic_ns() > before
print("PR3_ENTROPY_CLOCK_OK wall_ns=%d" % wall)
''')
            transfer(disk, 'import', '/work/integration.py', script)
            transfer(disk, 'import', '/work/no_rng.py', ROOT / 'tests/fixtures/cpython_py3_b1/entropy_probe.py')
            # Exercise all loaders affected by the boot_info extension; only one runs Python.
            for image, iso in [('xos.img', False), ('xos.iso', True), ('xos-install.iso', True)]:
                guest = Guest(system / image, prefix + '/' + image, work_disk=disk, iso=iso)
                guest.expect(b'xos64> ', timeout=40)
                assert b'width=800 height=600 stride=3200' in guest.output
                send_bytes(guest, b'run\r')
                guest.expect_supervisor(trace=True, timeout=40)
                pump(guest, 1.5)
                baseline = resources(guest)
                if not iso:
                    python_probe()
                    assert resources(guest) == baseline
                    mark('existing_cpython_entropy_and_realtime_before_display')
                output = command(guest, 'display-start', b'result=0')
                service = int(re.search(rb'\[display-start\] pid=(\d+) result=0', output)[1])
                guest.expect(b'[display-service] ready file=denied block=denied spawn=denied')
                with_service = resources(guest)
                output = command(guest, 'exec gfxdemo check', b'kind=exited code=0')
                assert len(re.findall(rb'\[gfx-check\] [^\n]*=pass', output)) == 23, output[-2200:]
                assert resources(guest) == with_service
                if not iso:
                    command(guest, 'exec gfxdemo deny', b'kind=exited code=0')
                    command(guest, 'exec gfxdemo threads', b'[gfx] threads=pass')
                    python_probe()
                    assert resources(guest) == with_service
                    mark('display_permissions_threads_and_cpython_coexist')
                command(guest, 'exec gfxdemo stop', b'kind=exited code=0')
                command(guest, 'wait ' + str(service), b'kind=exited code=0')
                assert resources(guest) == baseline
                mark(image + '_display_service_present_checks_and_reclamation')
                (out / (image + '.serial.log')).write_bytes(guest.output)
                guest.close()
                guest = None
            guest = Guest(system / 'xos.img', prefix + '/no_rng', cpu='qemu64', work_disk=disk)
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r'); guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest)
            output = command(guest, 'python3 /work/no_rng.py unsupported', b'kind=exited code=', timeout=120)
            assert b'PY3_B1_UNSUPPORTED_FAILURE_OK' in output and b'kind=exited code=0' in output, output[-1800:]
            assert resources(guest) == baseline
            mark('no_rdrand_truthful_failure_not_display_dispatch')
            (out / 'no_rng.serial.log').write_bytes(guest.output)
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        if guest is not None:
            (out / 'last.serial.log').write_bytes(guest.output)
            guest.close()
        (out / 'guest_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
