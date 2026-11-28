#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise authenticated publication, immutable staging and real GNU execution.

The COM1 authority backend here is an explicit developer fixture. Independent
UID provider qualification is recorded separately by P1-C; this runner never
promotes its same-UID Python object to a production authority claim.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def loadable(path):
    data = path.read_bytes()
    assert data[:7] == b'\x7fELF\x02\x01\x01'
    entry, phoff = struct.unpack_from('<QQ', data, 24)
    stride, count = struct.unpack_from('<HH', data, 54)
    assert stride == 56 and phoff + stride * count <= len(data)
    segments = []
    for ordinal in range(count):
        kind, flags, offset, address, physical, size, memory, alignment = struct.unpack_from(
            '<IIQQQQQQ', data, phoff + ordinal * stride)
        if kind == 1:
            assert offset + size <= len(data)
            segments.append({'flags': flags, 'address': address, 'physical': physical, 'size': size,
                             'memory': memory, 'alignment': alignment,
                             'sha256': hashlib.sha256(data[offset:offset + size]).hexdigest()})
    return {'entry': entry, 'segments': segments}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system-build', 'system-source', 'sdk', 'profile', 'xypm-build',
                 'v1-distribution', 'v2-distribution', 'trust', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('fault-xypm-build', 'test-private-key', 'test-other-key', 'v1-signature', 'v2-signature'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--official', action='store_true')
    args = parser.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path) and name != 'output': setattr(args, name, value.resolve(strict=True))
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(args.system_source / 'scripts'), str(args.system_source / 'tests'),
                   str(ROOT / 'scripts'), str(ROOT / 'tests')]
    from boot_smoke import Guest
    from task_smoke import pump, send_bytes
    from pumpkin_anchored_guest import binding, packet, realm, blank, frame_size, header, mark_struct
    from pumpkin_anchored_guest import ready, read, publish, finish, result_codes
    from pumpkin_provisioning_guest import make_disk
    from pumpkin_generation_authority import generation_authority, generation_mark, publish_result
    from xos_app import application_sdk_check
    from xypm_format import canonical, load_json, verify_package
    from xypm_image import Disk
    from xypm_release import DOMAIN, sign, trust_config, trust_header

    profile, trust = load_json(args.profile), trust_config(load_json(args.trust))
    if args.official:
        assert trust['repository_id'] == 'xos.official'
        assert args.v1_signature and args.v2_signature
        assert not args.test_private_key and not args.test_other_key and not args.fault_xypm_build
    else:
        assert trust['repository_id'].startswith('xos.test.')
        assert args.test_private_key and args.test_other_key and args.fault_xypm_build
    sdk_bound = application_sdk_check(args.sdk, profile)
    system_bound = binding(args.system_build)
    manifest = load_json(args.system_build / 'manifest.json')
    assert manifest.get('pumpkin_provisioning_store') == 1
    assert manifest.get('pumpkin_launch_probe') is True
    assert manifest.get('pumpkin_launch_storage_lease') == {
        'profile': 'launch_acceptance', 'duration_ns': 300_000_000_000}
    raw_supervisor = args.system_build / 'user_supervisor.elf'
    stripped_supervisor = args.system_build / 'user_supervisor.image.elf'
    assert loadable(raw_supervisor) == loadable(stripped_supervisor)
    assert stripped_supervisor.stat().st_size <= 131072
    inputs = {}

    def remember(path):
        path = Path(path)
        assert path.is_file() and not path.is_symlink()
        inputs[str(path)] = digest(path)

    for path in (Path(__file__), ROOT / 'scripts/xypm_release.py', args.profile, args.trust,
                 args.system_build / 'manifest.json', args.sdk / 'manifest.json'):
        remember(path)

    def installer(folder):
        project = folder / 'project'
        receipt = load_json(project / 'build/build_receipt.json')
        executable = project / receipt['output']
        assert receipt['output_sha256'] == digest(executable)
        assert receipt['sdk_tree_sha256'] == sdk_bound['tree_sha256']
        assert receipt['sdk_manifest_sha256'] == sdk_bound['sdk_manifest_sha256']
        assert receipt['profile_sha256'] == hashlib.sha256(canonical(profile)).hexdigest()
        assert (project / 'src/xypm_repository_trust.hpp').read_text() == trust_header(trust)
        for name, expected in receipt['inputs'].items():
            assert digest(project / name) == expected
            remember(project / name)
        for path in (executable, project / 'build/build_receipt.json', folder / 'manifest.json', folder / 'xypm.xpk'):
            remember(path)
        packed = verify_package(folder / 'xypm.xpk', profile)
        assert packed['sha256'] == load_json(folder / 'manifest.json')['sha256']
        return executable

    executable = installer(args.xypm_build)
    fault_executable = installer(args.fault_xypm_build) if args.fault_xypm_build else None
    repositories = output / 'repositories'
    repositories.mkdir()
    now = int(time.time())
    for sequence, directory, signature in ((1, args.v1_distribution, args.v1_signature),
                                           (2, args.v2_distribution, args.v2_signature)):
        metadata = load_json(directory / 'report.json')
        assert metadata['status'] == 'unsigned_distribution_built'
        assert metadata['generation_id'] == 1100 + sequence
        assert metadata['package_sha256'] == digest(directory / 'application.xpk')
        assert metadata['generation_sha256'] == digest(directory / 'repository/generation.bin')
        assert metadata['profile_sha256'] == hashlib.sha256(canonical(profile)).hexdigest()
        destination = repositories / ('v' + str(sequence))
        shutil.copytree(directory / 'repository', destination)
        shutil.copyfile(directory / 'lock.json', destination / 'lock.json')
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.name != 'report.json': remember(path)
        remember(directory / 'report.json')
        if signature:
            for name in ('release.json', 'release.sig'):
                remember(signature / name)
                shutil.copyfile(signature / name, destination / name)
        else:
            signed = output / ('test_signature_' + str(sequence))
            sign(destination, destination / 'lock.json', destination / 'generation.bin', trust,
                 args.test_private_key, sequence, now - 60, now + 86400, signed, profile)
            for name in ('release.json', 'release.sig'): shutil.copyfile(signed / name, destination / name)

    def raw_test_signature(directory, private, changes=None):
        assert not args.official
        metadata = load_json(directory / 'release.json')
        metadata.update(changes or {})
        metadata['index_sha256'] = digest(directory / 'index.json')
        metadata['lock_sha256'] = digest(directory / 'lock.json')
        body = canonical(metadata)
        message = output / 'test_only_signing_message'
        message.write_bytes(DOMAIN + body)
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(private),
                        '-in', str(message), '-out', str(directory / 'release.sig')],
                       check=True, capture_output=True)
        (directory / 'release.json').write_bytes(body)
        message.unlink()

    if not args.official:
        for name in ('altered', 'expired', 'untrusted', 'cycle', 'conflict', 'missing', 'changedobject'):
            selected = repositories / name
            shutil.copytree(repositories / 'v2', selected)
            if name == 'altered':
                with (selected / 'release.json').open('ab') as stream: stream.write(b' ')
            elif name == 'expired':
                raw_test_signature(selected, args.test_private_key,
                                   {'issued_at': now - 172800, 'expires_at': now - 86400})
            elif name == 'untrusted':
                raw_test_signature(selected, args.test_other_key)
            elif name in ('cycle', 'conflict'):
                index = load_json(selected / 'index.json')
                first = {'id': 'test.base', 'upstream_version': '1', 'revision': 0,
                         'sha256': '1' * 64, 'size': 512, 'required_features': [], 'runtime_dependencies': []}
                second = copy.deepcopy(first)
                second.update(id='test.next' if name == 'cycle' else 'test.base',
                              upstream_version='2', sha256='2' * 64)
                identity = lambda value: {field: value[field] for field in ('id', 'upstream_version', 'revision', 'sha256')}
                if name == 'cycle':
                    first['runtime_dependencies'] = [identity(second)]
                    second['runtime_dependencies'] = [identity(first)]
                index['packages'] = [first, second]
                (selected / 'index.json').write_bytes(canonical(index))
                lock = {'format_version': 1, 'target_profile': profile['id'],
                        'index_sha256': digest(selected / 'index.json'),
                        'roots': [first['sha256']] if name == 'cycle' else [first['sha256'], second['sha256']],
                        'packages': [first['sha256'], second['sha256']]}
                (selected / 'lock.json').write_bytes(canonical(lock))
                raw_test_signature(selected, args.test_private_key)
            else:
                package = next(selected.glob('*.xpk'))
                if name == 'missing': package.unlink()
                else:
                    body = bytearray(package.read_bytes())
                    # The middle lies in the large ELF payload, leaving TAR and
                    # manifest syntax intact so the payload hash is the cause.
                    body[len(body) // 2] ^= 1
                    package.write_bytes(body)

    report = {'status': 'failed', 'scope': 'real native guest signed distribution + GNU application execution',
              'official': args.official, 'repository_id': trust['repository_id'],
              'system': system_bound, 'sdk': sdk_bound, 'inputs': inputs,
              'backing_lease': manifest['pumpkin_launch_storage_lease'],
              'per_request_deadline_ns': 5_000_000_000,
              'installer_staging_deadline_ns': 120_000_000_000,
              'authority_scope': 'explicit developer COM1 generation authority; production UID provider tested separately',
              'strip_proof': loadable(stripped_supervisor), 'cases': {}}
    disk = output / 'work.img'
    provider_root = output / 'developer_authority'
    provider_root.mkdir(mode=0o700)
    authority = generation_authority(provider_root, realm, provisioning=True)
    authority.provision()

    def import_file(image, destination, source):
        parts = destination.strip('/').split('/')
        for count in range(1, len(parts)):
            parent = '/' + '/'.join(parts[:count])
            if image.info(parent) is None: image.command('mkdir', parent)
        image.command('import', destination, source)

    def decode_mark(data):
        return None if data == blank else generation_mark(*mark_struct.unpack(data), provisioning=True)

    def boot(scenario):
        name = 'scenario_' + str(scenario)
        evidence = {'status': 'failed', 'scenario': scenario, 'events': [], 'diagnostics': {}}
        report['cases'][name] = evidence
        guest = Guest(args.system_build / 'xos-install.iso', name, iso=True, work_disk=disk, log_dir=output)
        try:
            evidence['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=35)
            offset = len(guest.output)
            send_bytes(guest, b'run\r')
            until = time.monotonic() + 310
            for sequence in range(100):
                while True:
                    marker = guest.output.find(b'PKA1', offset)
                    if marker >= 0 and len(guest.output) >= marker + frame_size: break
                    assert time.monotonic() < until, name + ': bounded serial exchange deadline'
                    pump(guest, 0.04)
                data = bytes(guest.output[marker:marker + frame_size])
                magic, version, operation, result, observed_sequence = header.unpack_from(data)
                assert (magic, version, observed_sequence) == (b'PKA1', 1, sequence)
                expected = data[header.size:header.size + mark_struct.size]
                value = data[-mark_struct.size:]
                offset = marker + frame_size
                if operation == ready:
                    assert sequence == 0 and result == 0 and expected == blank and value == blank
                    reply = packet(ready, scenario, sequence)
                elif operation == read:
                    assert result == 0 and expected == blank and value == blank
                    selected = authority.read()
                    encoded = blank if selected is None else mark_struct.pack(
                        selected.realm, selected.revision, selected.length, selected.checksum)
                    evidence['events'].append({'read_revision': None if selected is None else selected.revision})
                    reply = packet(read, 1 if selected is None else 0, sequence, encoded)
                elif operation == publish:
                    assert result == 0
                    previous, candidate = decode_mark(expected), decode_mark(value)
                    assert candidate is not None and previous == authority.read()
                    outcome = authority.publish(previous, candidate)
                    assert outcome == publish_result.committed
                    evidence['events'].append({'published_revision': candidate.revision, 'outcome': outcome.name})
                    reply = packet(publish, result_codes[outcome], sequence)
                else:
                    assert operation == finish and expected == blank and value == blank
                    evidence['finish_code'] = result
                    send_bytes(guest, packet(finish, 0, sequence))
                    pump(guest, 0.15)
                    guest.qmp('quit')
                    assert guest.process.wait(timeout=10) == 0
                    assert result == 1, name + ': production guest fixture failed: ' + str(result)
                    evidence['status'] = 'fixture_passed'
                    evidence['authority_revision'] = authority.read().revision
                    break
                send_bytes(guest, reply)
            else: raise AssertionError('bounded protocol sequence count exhausted')
        finally:
            guest.close()
            with Disk(disk, output, read_only=True) as image:
                paths = ['application.out', 'application.err']
                paths += [f'run_{ordinal}.{suffix}' for ordinal in range(8 if scenario == 33 else 1) for suffix in ('out', 'err')]
                for path in paths:
                    if image.info('/dist/' + path) is not None:
                        exported = image.export('/dist/' + path)
                        destination = output / (name + '_' + path)
                        exported.rename(destination)
                        evidence['diagnostics'][path] = {'sha256': digest(destination),
                            'text': destination.read_text(errors='replace')}
            (output / (name + '.json')).write_text(json.dumps(evidence, indent=2) + '\n')
        diagnostics = evidence['diagnostics']
        revision = 2 if scenario in (35, 36) else 1
        assert diagnostics['application.out']['text'] == f'P1D_EXTERNAL_APPLICATION revision={revision} libc=GNU\n'
        assert 'legacy_visible_owned=0 ' in diagnostics['application.err']['text']
        pair = re.search(r'created_backing_send=(\d+) created_backing_receive=(\d+)\n', diagnostics['application.err']['text'])
        assert pair and int(pair[1]) > 0 and int(pair[2]) > 0 and pair[1] != pair[2]
        if scenario in (32, 35):
            assert f'Authenticated generation installed: {1100 + revision} sequence={revision}' in diagnostics['run_0.out']['text']
        elif scenario == 33:
            expected_errors = ['daemon did not grant catalog publisher authority',
                'repository Ed25519 signature rejected', 'repository metadata is expired or not yet valid',
                'repository Ed25519 signature rejected', 'repository dependency cycle',
                'dependency closure selects conflicting package versions', 'cannot open repository file', 'payload hash mismatch']
            for ordinal, expected_error in enumerate(expected_errors):
                assert expected_error in diagnostics[f'run_{ordinal}.err']['text'], (ordinal, diagnostics[f'run_{ordinal}.err'])
        elif scenario == 34:
            assert 'xypm-test: distribution_staging_stop=1' in diagnostics['run_0.out']['text']
        else:
            assert 'repository metadata rollback rejected' in diagnostics['run_0.err']['text']
        assert evidence['authority_revision'] == (3 if revision == 2 else 2)
        evidence['status'] = 'passed'
        (output / (name + '.json')).write_text(json.dumps(evidence, indent=2) + '\n')
        print('PASS signed distribution ' + name + ': real GNU revision ' + str(revision), flush=True)

    try:
        make_disk(disk)
        with Disk(disk, output) as image:
            import_file(image, '/usr/bin/xypm', executable)
            if fault_executable: import_file(image, '/usr/bin/xypm-fault', fault_executable)
            for path in sorted(repositories.rglob('*')):
                if path.is_file():
                    remember(path)
                    import_file(image, '/dist/' + path.relative_to(repositories).as_posix(), path)
        for scenario in ((32, 35, 36) if args.official else (32, 33, 34, 35, 36)):
            boot(scenario)
        assert binding(args.system_build) == system_bound
        assert application_sdk_check(args.sdk, profile) == sdk_bound
        assert all(digest(path) == expected for path, expected in inputs.items())
        report['status'] = 'passed'
    finally:
        if disk.exists(): report['final_disk_sha256'] = digest(disk)
        report['inputs'] = inputs
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
