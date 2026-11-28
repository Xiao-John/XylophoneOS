#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify P1-A with ordinary native clients and replay their actual records.

The optional --network profile reads the real service's current static
configuration. It sends no application network traffic and records no packets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_observation_probe import INPUTS
from make_work_disk import create_fat32
from observation_replay import canonical, evaluate
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer
from xos_app import tree_receipt

CASES = ('native', 'authorized', 'denials', 'quota', 'lifecycle', 'deadline', 'exec')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(observation, number, out):
    """Record a deterministic non-model proposal against the real guest sample."""
    item = observation['records'][0] if observation['records'] else {
        'kind': 'process', 'object_id': observation['source']['pid'], 'generation': 1, 'scope': 'self'}
    target = {key: item[key] for key in ('kind', 'object_id', 'generation')}
    policy_target = {key: item[key] for key in ('kind', 'object_id')}
    sample = {
        'schema_version': 1, 'validator_version': 1, 'policy_version': 1,
        'logical_time_ns': observation['logical_time_ns'],
        'policy': {'caller_pid': observation['caller_pid'], 'allowed_actions': ['inspect'],
                   'allowed_scopes': [item['scope']], 'allowed_targets': [policy_target],
                   'max_observation_age_ns': 5_000_000_000},
        'observation': observation,
        'proposal': {'schema_version': 1, 'proposal_id': number,
                     'observation_id': observation['observation_id'], 'source': observation['source'],
                     'caller_pid': observation['caller_pid'], 'target': target, 'action': 'inspect',
                     'expires_ns': observation['valid_until_ns']},
    }
    first = canonical(evaluate(sample))
    second = canonical(evaluate(json.loads(canonical(sample))))
    expected = 'accepted_proposal' if observation['status'] == 'ok' else observation['status']
    result = json.loads(first)
    if first != second or result['status'] != expected or result['execution_authority'] or result['automatic_retry']:
        raise AssertionError(f'guest replay mismatch: {result}, expected {expected}')
    name = f'replay_{number:04d}'
    (out / (name + '.json')).write_bytes(canonical(sample) + b'\n')
    (out / (name + '_result.json')).write_bytes(first + b'\n')
    return {'record': name + '.json', 'result': name + '_result.json', 'status': result['status'],
            'input_sha256': result['input_sha256'], 'repeat_identical': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeat', type=int, choices=range(1, 9), default=3)
    parser.add_argument('--network', action='store_true', help='run the six-source case against live static Net2')
    args = parser.parse_args()
    system, fixture, out = args.system.resolve(), args.fixture.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build'); out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runs': [], 'replays': [], 'runner_sha256': sha(Path(__file__)),
              'network': 'live_static_configuration' if args.network else 'absent_typed_unavailable',
              'not_run': ['model_generation', 'autonomous_writes', 'installed_profile', 'fork_generation_guest',
                          'global_atomic_snapshot', 'runtime_ELF_load', 'trust_bundle_load']}
    guest = None
    try:
        manifest = json.loads((system / 'manifest.json').read_bytes())
        receipt = json.loads((fixture / 'receipt.json').read_bytes())

        def verify_inputs():
            for path, digest in manifest['sources'].items():
                if sha(ROOT / path) != digest:
                    raise ValueError('system source changed: ' + path)
            for path, value in manifest['artifacts'].items():
                if sha(system / path) != value['sha256']:
                    raise ValueError('system artifact changed: ' + path)
            if receipt['sources'] != {path: sha(ROOT / path) for path in INPUTS}:
                raise ValueError('fixture source changed')
            if receipt['status'] != 'built_not_run' or receipt['libc_linked']:
                raise ValueError('fixture build profile mismatch')
            if tree_receipt(system / 'sdk')[0] != receipt['sdk_tree_sha256']:
                raise ValueError('fixture SDK changed')
            for path, digest in receipt['artifacts'].items():
                if sha(fixture / path) != digest:
                    raise ValueError('fixture artifact changed')

        verify_inputs()
        report.update(system_build_id=manifest['build_id'], iso_sha256=sha(system / 'xos-install.iso'),
                      system_manifest_sha256=sha(system / 'manifest.json'),
                      fixture_receipt_sha256=sha(fixture / 'receipt.json'), sdk_tree_sha256=receipt['sdk_tree_sha256'])
        with tempfile.TemporaryDirectory(prefix='xos_observation_guest_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/observe.elf', fixture / 'observation.elf')
            guest = Guest(system / 'xos-install.iso', 'guest', iso=True, work_disk=disk,
                          qmp_enabled=False, network=args.network, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2)
            network_pid = 0
            if args.network:
                # A sealed static profile starts its owned service at boot.
                # Use that trusted supervisor announcement; start explicitly
                # only when this image has not already announced an owner.
                announced = list(re.finditer(rb'\[net-start\] pid=(\d+)', guest.output))
                if len(announced) > 1:
                    raise AssertionError('ambiguous network service bootstrap')
                if announced:
                    began = announced[0].start()
                    network_pid = int(announced[0][1])
                else:
                    began = len(guest.output)
                    started = command(guest, 'net-start 41', b'[net-start] pid=', timeout=60)
                    network_pid = int(re.search(rb'\[net-start\] pid=(\d+)', started)[1])
                guest.expect(b'[net] ready native_v2=1', start=began, timeout=60)
            baseline = resources(guest); report['baseline'] = baseline
            cases = ('network',) if args.network else CASES
            for round_number in range(args.repeat):
                for mode in cases:
                    line = 'exec-driver /bin/observe.elf ' + mode
                    if args.network: line += ' ' + str(network_pid)
                    output = command(guest, line, b'kind=exited code=', timeout=60)
                    exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
                    if output.count(('OBS_PASS ' + mode).encode()) != 1 or b'OBS_FAIL ' in output or b'OBS_NATIVE_FAIL ' in output or exits != [b'0']:
                        raise AssertionError(output[-8000:])
                    if mode == 'native':
                        for marker in (b'OBS_NATIVE_SELF_PASS', b'OBS_NATIVE_SCOPE_PASS', b'OBS_NATIVE_FORMAT_PASS', b'OBS_NATIVE_DEADLINE_PASS'):
                            if marker not in output: raise AssertionError('missing native check: ' + repr(marker))
                    if mode == 'exec' and any(marker not in output for marker in
                            (b'OBS_FAILED_EXEC_RETAINED', b'OBS_SUCCESSFUL_EXEC_GENERATION')):
                        raise AssertionError('missing real exec identity checks')
                    samples = [json.loads(value) for value in re.findall(rb'OBS_JSON (\{[^\r\n]+\})', output)]
                    for sample in samples:
                        report['replays'].append(replay(sample, len(report['replays']) + 1, out))
                    if mode in ('authorized', 'network') and len(samples) != 6:
                        raise AssertionError('six actual observations required')
                    if mode == 'network':
                        current = [item for sample in samples for item in sample['records'] if item['kind'] == 'network']
                        if len(current) != 1 or current[0]['object_id'] != network_pid or current[0]['data']['state'] != 'ready':
                            raise AssertionError('live static network not observed')
                    for _ in range(30):
                        actual = resources(guest)
                        if actual == baseline: break
                        pump(guest, 0.1)
                    else:
                        raise AssertionError(f'resources {actual}, expected {baseline}')
                    report['runs'].append({'round': round_number, 'case': mode, 'resources': actual,
                                           'observations': len(samples), 'status': 'passed'})
            verify_inputs(); report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest: guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS observation guest:', len(report['runs']), 'cases;', len(report['replays']), 'identical replays')


if __name__ == '__main__':
    main()
