#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify independent clients, scanout damage, real input and owner recovery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_mobius_multiwindow_probe import INPUTS
from interactium_guest import write_png
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import pump, send_bytes
from work_disk import transfer
from xos_app import tree_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--threading-sdk', type=Path,
                        help='verify a separately rebuilt threading SDK and POSIX/newlib client')
    args = parser.parse_args()
    system, fixture, out = args.system.resolve(), args.fixture.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build'); out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('XOS_QMP_TRANSPORT', 'pipe')
    report = {'status': 'failed', 'checks': [], 'screenshots': [], 'runner_sha256': sha(Path(__file__)),
              'profile': 'two independent ordinary SDK clients, current production Interactium service',
              'not_run': ['Qt package rebuild', 'hardware GPU', 'SMP', 'long_duration_stress', 'glass_blur']}
    guest = None
    try:
        manifest = json.loads((system / 'manifest.json').read_bytes())
        receipt = json.loads((fixture / 'receipt.json').read_bytes())
        selected_sdk = args.threading_sdk.resolve() if args.threading_sdk else system / 'sdk'
        report['client_sdk_profile'] = 'threading_posix_newlib' if args.threading_sdk else 'ordinary_native_no_libc'

        def verify_inputs():
            for path, digest in manifest['sources'].items():
                if sha(ROOT / path) != digest: raise ValueError('system source changed: ' + path)
            for path, entry in manifest['artifacts'].items():
                if sha(system / path) != entry['sha256']: raise ValueError('system artifact changed: ' + path)
            if receipt['sources'] != {p: sha(ROOT / p) for p in INPUTS}:
                raise ValueError('fixture source changed')
            if (receipt['status'] != 'built_not_run' or
                    receipt['libc_linked'] != bool(args.threading_sdk) or
                    receipt['client_sdk_profile'] != report['client_sdk_profile']):
                raise ValueError('fixture profile mismatch')
            if tree_receipt(selected_sdk)[0] != receipt['sdk_tree_sha256']:
                raise ValueError('fixture SDK changed')
            if args.threading_sdk:
                sdk_manifest = json.loads((selected_sdk / 'manifest.json').read_bytes())
                if sdk_manifest['profile'] != 'xos-threading-v1-experimental':
                    raise ValueError('unexpected alternate SDK profile')
                for path, digest in sdk_manifest['inputs'].items():
                    if sha(ROOT / path) != digest: raise ValueError('threading SDK source changed: ' + path)
            for path, digest in receipt['artifacts'].items():
                if sha(fixture / path) != digest: raise ValueError('fixture artifact changed')

        verify_inputs()
        report.update(system_build_id=manifest['build_id'], iso_sha256=sha(system / 'xos-install.iso'),
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      fixture_receipt_sha256=sha(fixture / 'receipt.json'), sdk_tree_sha256=receipt['sdk_tree_sha256'])

        def mark(name, **values):
            report['checks'].append({'case': name, 'status': 'passed', **values})

        def snapshot(name):
            pump(guest, .25)
            ppm = out / (name + '.ppm'); png = out / (name + '.png')
            guest.qmp('screendump', {'filename': str(ppm)})
            raw = ppm.read_bytes(); header = b'P6\n800 600\n255\n'
            if not raw.startswith(header) or len(raw) != len(header) + 800 * 600 * 3:
                raise AssertionError('unexpected scanout dimensions')
            pixels = raw[len(header):]; write_png(png, pixels, 800, 600)
            report['screenshots'].append({'file': png.name, 'sha256': sha(png)})
            return lambda x, y: tuple(pixels[(y * 800 + x) * 3:(y * 800 + x + 1) * 3])

        def event(kind, data):
            guest.qmp('input-send-event', {'events': [{'type': kind, 'data': data}]})
            pump(guest, .04)

        def move(x, y):
            for _ in range(9):
                event('rel', {'axis': 'x', 'value': -100})
                event('rel', {'axis': 'y', 'value': -100})
            for axis, distance in (('x', x), ('y', y)):
                while distance:
                    step = min(distance, 80); distance -= step
                    event('rel', {'axis': axis, 'value': step})

        def click(x, y):
            move(x, y); event('btn', {'button': 'left', 'down': True})
            event('btn', {'button': 'left', 'down': False}); pump(guest, .1)

        def key(name, role, marker=None):
            start = len(guest.output)
            event('key', {'down': True, 'key': {'type': 'qcode', 'data': name}})
            event('key', {'down': False, 'key': {'type': 'qcode', 'data': name}})
            if marker: guest.expect((marker + ' role=' + role).encode(), start=start, timeout=25)
            pump(guest, .1)
            return bytes(guest.output[start:])

        def spawn(role, service):
            start = len(guest.output)
            prefix = ('MOBIUS_READY role=' + role).encode()
            command(guest, f'spawn-file /bin/mobwin.elf {role} {service}', prefix, timeout=30)
            # Serial fields are separate writes. The marker alone does not
            # imply the PID and token at the end of the line have arrived.
            ready = guest.output.find(prefix, start)
            guest.expect(b'\n', start=ready, timeout=15)
            output = bytes(guest.output[start:])
            if args.threading_sdk:
                assert ('MOBIUS_THREAD_RUNTIME_PASS role=' + role).encode() in output
            match = re.search(rb'MOBIUS_READY role=\w+ pid=(\d+) window=(\d+)', output)
            if not match: raise AssertionError(output)
            return tuple(map(int, match.groups()))

        def reclaim(expected):
            for _ in range(30):
                actual = resources(guest)
                if actual == expected: return actual
                pump(guest, .1)
            raise AssertionError(f'resources {actual}, expected {expected}')

        with tempfile.TemporaryDirectory(prefix='xos_mobius_multiwindow_') as temporary:
            disk = Path(temporary) / 'work.img'; create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/mobwin.elf', fixture / 'mobius_multiwindow.elf')
            guest = Guest(system / 'xos-install.iso', 'guest', iso=True, work_disk=disk, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks'); command(guest, 'audio stop', b'xsh> ')
            initial = resources(guest); report['initial_resources'] = initial
            started = command(guest, 'interactium-start', b'[interactium-service] ready', timeout=45)
            service = int(re.search(rb'\[interactium-start\] pid=(\d+)', started)[1])
            display = int(re.search(rb'\[display-start\] pid=(\d+)', started)[1])
            baseline = resources(guest); report['service_resources'] = baseline
            left, left_window = spawn('left', service)
            with_left = resources(guest)
            right, right_window = spawn('right', service)
            if left == right or left_window == right_window: raise AssertionError('independent identities required')
            pixels = snapshot('two_independent_apps')
            assert pixels(100, 100) == (40, 96, 192) and pixels(400, 240) == (208, 104, 48)
            assert pixels(300, 240) == (208, 104, 48) and pixels(700, 400) == (39, 51, 66)
            mark('two_independent_pids_render', pids=[left, right], windows=[left_window, right_window])
            if args.threading_sdk:
                mark('matching_threading_crt_newlib_pthread_tls_errno_and_join')
            completed = command(guest, f'exec-file /bin/mobwin.elf negative {service} {left_window}',
                                b'kind=exited code=0', timeout=30)
            assert b'MOBIUS_NEGATIVE_PASS role=negative checks=11' in completed
            mark('foreign_tokens_alpha_resize_retirement_and_stale_tokens', checks=11)
            for role, pid, marker in [('wrong-peer', service + 1, b'MOBIUS_WRONG_PEER_PASS'),
                                      ('malformed', service, b'MOBIUS_MALFORMED_PASS')]:
                completed = command(guest, f'exec-file /bin/mobwin.elf {role} {pid}',
                                    b'kind=exited code=0', timeout=15)
                assert marker in completed
                mark(role)
            click(100, 120)
            output = key('a', 'left', 'MOBIUS_DAMAGE')
            assert b'MOBIUS_KEY role=right code=30' not in output
            pixels = snapshot('left_focus_and_damage')
            assert pixels(150, 150) == (32, 192, 112) and pixels(300, 240) == (40, 96, 192)
            mark('focus_exclusive_keyboard_and_z_order')
            key('s', 'left', 'MOBIUS_STAGED')
            assert snapshot('pending_frame_hidden')(150, 150) == (32, 192, 112)
            key('c', 'left', 'MOBIUS_CANCELLED')
            assert snapshot('cancel_keeps_front')(150, 150) == (32, 192, 112)
            key('s', 'left', 'MOBIUS_STAGED'); key('p', 'left', 'MOBIUS_COMMITTED')
            assert snapshot('committed_damage')(150, 150) == (192, 32, 192)
            mark('copy_commit_and_cancel_front_visibility')
            click(500, 350)
            start = len(guest.output)
            event('key', {'down': True, 'key': {'type': 'qcode', 'data': 'b'}})
            guest.expect(b'MOBIUS_KEY role=right code=48', start=start, timeout=15)
            click(100, 120)
            event('key', {'down': False, 'key': {'type': 'qcode', 'data': 'b'}})
            guest.expect(b'MOBIUS_RELEASE role=right code=48', start=start, timeout=15)
            assert b'MOBIUS_RELEASE role=left code=48' not in bytes(guest.output[start:])
            mark('key_release_retains_press_owner_after_focus_change')
            move(100, 120); start = len(guest.output)
            event('btn', {'button': 'left', 'down': True}); move(500, 350)
            event('btn', {'button': 'left', 'down': False}); pump(guest, .2)
            capture = bytes(guest.output[start:])
            assert b'MOBIUS_POINTER role=left buttons=1' in capture
            assert b'MOBIUS_POINTER role=right buttons=1' not in capture
            mark('pointer_drag_capture_retains_press_owner')
            click(100, 120); key('r', 'left', 'MOBIUS_RESIZED'); key('m', 'left', 'MOBIUS_MOVED')
            pixels = snapshot('resize_and_move')
            assert pixels(70, 90) == (39, 51, 66) and pixels(450, 370) == (40, 96, 192)
            assert pixels(500, 350) == (208, 104, 48)
            mark('resize_and_move_restore_old_extents')
            click(500, 350); key('s', 'right', 'MOBIUS_STAGED'); key('x', 'right', 'MOBIUS_CRASH')
            command(guest, f'wait {right}', b'kind=faulted', timeout=30)
            reclaim(with_left)
            pixels = snapshot('crash_preserves_other_app')
            assert pixels(520, 370) == (39, 51, 66) and pixels(150, 150) == (40, 96, 192)
            output = key('a', 'left', 'MOBIUS_DAMAGE')
            assert b'MOBIUS_FAIL' not in output
            mark('fault_during_pending_frame_preserves_other_app_and_resources')
            key('q', 'left', 'MOBIUS_CLOSED'); command(guest, f'wait {left}', b'kind=exited code=0')
            reclaim(baseline)
            assert snapshot('closed_scene_restored')(150, 150) == (39, 51, 66)
            mark('close_revokes_surface_and_restores_exact_resources')
            left, _ = spawn('left', service)
            command(guest, f'kill {service}', b'kill: accepted')
            command(guest, f'wait {service}', b'kind=killed', timeout=30)
            guest.expect(b'MOBIUS_SERVICE_LOST role=left', timeout=15)
            command(guest, f'wait {left}', b'kind=exited code=0')
            with_display = resources(guest)
            mark('service_death_wakes_client_and_revokes_session')
            output = command(guest, 'spawn-file /bin/mobwin.elf stall 0', b'MOBIUS_STALL_READY', timeout=20)
            stalled = int(re.search(rb'\[loader\] started pid=(\d+)', output)[1])
            output = command(guest, f'exec-file /bin/mobwin.elf timeout {stalled}',
                             b'kind=exited code=0', timeout=15)
            assert b'MOBIUS_TIMEOUT_PASS' in output
            command(guest, f'kill {stalled}', b'kill: accepted')
            command(guest, f'wait {stalled}', b'kind=killed')
            reclaim(with_display); mark('live_unresponsive_service_obeys_original_deadline')
            # The existing display service remains owned and alive. Restart
            # only its ordinary compositor client; interactium-start creates
            # a display service as well and correctly rejects a second owner.
            restarted = command(guest, 'spawn interactiumd', b'[interactium-service] ready', timeout=30)
            new_service = int(re.search(rb'\[loader\] started pid=(\d+)', restarted)[1])
            assert new_service != service
            left, _ = spawn('left', new_service); right, _ = spawn('right', new_service)
            pixels = snapshot('fresh_service_epoch')
            assert pixels(100, 100) == (40, 96, 192) and pixels(400, 240) == (208, 104, 48)
            click(500, 350); key('q', 'right', 'MOBIUS_CLOSED')
            command(guest, f'wait {right}', b'kind=exited code=0')
            key('q', 'left', 'MOBIUS_CLOSED'); command(guest, f'wait {left}', b'kind=exited code=0')
            command(guest, f'kill {new_service}', b'kill: accepted')
            command(guest, f'wait {new_service}', b'kind=killed')
            reclaim(with_display); mark('fresh_service_epoch_two_clients_and_cleanup')
            output = command(guest, 'exec gfxdemo check', b'[gfx] checks=pass', timeout=30)
            assert b'kind=exited code=0' in output
            reclaim(with_display); mark('legacy_exclusive_display_compatibility')
            command(guest, f'kill {display}', b'kill: accepted')
            command(guest, f'wait {display}', b'kind=killed')
            reclaim(initial); report['final_resources'] = initial
            if b'MOBIUS_FAIL' in guest.output: raise AssertionError('client reported a failed check')
            verify_inputs(); report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest: guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS Mobius multiwindow guest:', len(report['checks']), 'checks')


if __name__ == '__main__':
    main()
