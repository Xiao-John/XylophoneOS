#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify real loaded-trust snapshots and replay their production JSON in XOS.

This isolated glibc probe loads disposable CA bundles without network traffic.
Its local observation envelopes do not qualify remote IPC authorization or TLS
handshakes; those require their own matching evidence.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_observation_trust_probe import SOURCE_NAMES
from make_work_disk import create_fat32
from observation_guest import replay, sha
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer

CHECKS = (
    'null_context_zeroed', 'empty_store_zeroed', 'empty_identity_zeroed',
    'wrong_digest_unavailable', 'wrong_generation_unavailable',
    'malformed_der_unavailable', 'verified_store_load', 'verified_pin_owned_copy',
    'reload_preserves_loaded_identity', 'replacement_store_load',
    'selected_original', 'selected_replacement', 'authorized_rollback_selection',
    'detached_selection_unavailable', 'production_source_records',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('system', 'fixture', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--repeat', type=int, choices=range(1, 9), default=1)
    args = parser.parse_args()
    system, fixture, out = args.system.resolve(), args.fixture.resolve(), args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {
        'status': 'failed', 'profile': 'loaded_trust_snapshot', 'target': 'glibc',
        'scope': 'real CA loads, optional bridge, production sources and JSON, offline replay',
        'network': 'disabled', 'qmp_enabled': False, 'runs': [], 'replays': [],
        'runner_sha256': sha(Path(__file__)),
        'not_run': ['TLS_handshake', 'network_traffic', 'remote_IPC_authorization',
                    'model_generation', 'autonomous_writes', 'installed_profile'],
    }
    guest = None
    try:
        manifest_path, receipt_path = system / 'manifest.json', fixture / 'receipt.json'
        manifest = json.loads(manifest_path.read_bytes())
        receipt = json.loads(receipt_path.read_bytes())
        manifest_digest, receipt_digest = sha(manifest_path), sha(receipt_path)
        iso = system / 'xos-install.iso'
        iso_digest = sha(iso)

        def verify_inputs():
            if sha(manifest_path) != manifest_digest or sha(receipt_path) != receipt_digest:
                raise ValueError('system manifest or fixture receipt changed')
            if sha(iso) != iso_digest:
                raise ValueError('system ISO changed')
            for path, digest in manifest['sources'].items():
                if sha(ROOT / path) != digest:
                    raise ValueError('system source changed: ' + path)
            for path, value in manifest['artifacts'].items():
                if sha(system / path) != value['sha256']:
                    raise ValueError('system artifact changed: ' + path)
            if receipt['sources'] != {path: sha(ROOT / path) for path in SOURCE_NAMES}:
                raise ValueError('fixture source changed')
            if (receipt['status'], receipt['profile'], receipt['target']) != (
                    'built_not_run', 'loaded_trust_snapshot', 'glibc'):
                raise ValueError('fixture build profile mismatch')
            required = {'observation_trust.elf', 'observation_trust_data.hpp',
                        'trust-7.bin', 'trust-8.bin'}
            if not required.issubset(receipt['artifacts']):
                raise ValueError('fixture artifacts incomplete')
            for path, digest in receipt['artifacts'].items():
                if sha(fixture / path) != digest:
                    raise ValueError('fixture artifact changed: ' + path)
            if receipt['fixture_pins'] != {
                    generation: receipt['artifacts']['trust-' + generation + '.bin']
                    for generation in ('7', '8')}:
                raise ValueError('fixture pins do not identify the complete CA bundles')

        verify_inputs()
        report.update(system_build_id=manifest['build_id'], iso_sha256=iso_digest,
                      system_manifest_sha256=manifest_digest,
                      fixture_receipt_sha256=receipt_digest,
                      fixture_elf_sha256=receipt['artifacts']['observation_trust.elf'],
                      fixture_pins=receipt['fixture_pins'],
                      glibc_sdk_manifest_sha256=receipt['sdk_manifest_sha256'])
        with tempfile.TemporaryDirectory(prefix='xos_observation_trust_guest_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            transfer(disk, 'mkdir', '/bin')
            transfer(disk, 'import', '/bin/trust.elf', fixture / 'observation_trust.elf')
            guest = Guest(iso, 'guest', iso=True, work_disk=disk, qmp_enabled=False,
                          network=False, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2)
            baseline = resources(guest)
            report['baseline'] = baseline
            for round_number in range(args.repeat):
                output = command(guest, 'exec-driver /bin/trust.elf',
                                 b'kind=exited code=', timeout=60)
                run = {'round': round_number, 'case': 'loaded_trust_snapshot',
                       'status': 'failed', 'output': output.decode(errors='replace')}
                report['runs'].append(run)
                checks = re.findall(rb'OBS_TRUST_CHECK ([a-z0-9_]+) (PASS|FAIL)(?:\r?\n|$)', output)
                run['checks'] = [{'case': name.decode(), 'status': result.decode()}
                                 for name, result in checks]
                exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
                summaries = re.findall(rb'OBS_TRUST_PASS checks=(\d+)(?:\r?\n|$)', output)
                if (output.count(b'OBS_TRUST_CHECK ') != len(CHECKS) or
                        checks != [(name.encode(), b'PASS') for name in CHECKS] or
                        output.count(b'OBS_TRUST_PASS') != 1 or summaries != [b'15'] or
                        b'OBS_TRUST_FAIL' in output or exits != [b'0']):
                    raise AssertionError('trust checks, summary or exact exit mismatch: ' + repr(output[-8000:]))
                samples = [json.loads(value) for value in
                           re.findall(rb'OBS_JSON (\{[^\r\n]+\})', output)]
                run['observations'] = samples
                if output.count(b'OBS_JSON ') != 5 or len(samples) != 5:
                    raise AssertionError('five actual trust observations required')
                if [sample['status'] for sample in samples] != ['unavailable', 'ok', 'ok', 'ok', 'unavailable']:
                    raise AssertionError('trust selection lifecycle differs')
                successful = [sample for sample in samples if sample['status'] == 'ok']
                for sample, generation in zip(successful, (7, 8, 7)):
                    if len(sample['records']) != 1:
                        raise AssertionError('successful trust observation requires one record')
                    item = sample['records'][0]
                    if (item['kind'] != 'trust' or item['scope'] != 'application' or
                            item['object_id'] != generation or item['generation'] != generation or
                            item['data']['selection'] != 'loaded_snapshot' or
                            item['data']['digest'] != receipt['fixture_pins'][str(generation)]):
                        raise AssertionError('loaded trust generation, complete digest or scope mismatch')
                for sample in samples:
                    report['replays'].append(replay(sample, len(report['replays']) + 1, out))
                for _ in range(30):
                    actual = resources(guest)
                    if actual == baseline:
                        break
                    pump(guest, 0.1)
                else:
                    raise AssertionError(f'resources {actual}, expected {baseline}')
                run.update(resources=actual, status='passed')
            verify_inputs()
            report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS observation trust guest:', len(report['runs']), 'runs;',
          len(report['replays']), 'identical replays')


if __name__ == '__main__':
    main()
