#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify one native controller's real GNU generation activation and reclamation."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_dynamic_launcher import anchor_sdk, guest_path, sha
from make_work_disk import create_fat32
from process_smoke import command, resources
from sdk_receipt import tree_receipt, verify_sdk
from shell_launch_support import bind_system, relative_file
from task_smoke import pump, send_bytes
from work_disk import transfer

CASES = ('initial_generation_0', 'activate_1_preserves_old_pin', 'stale_sequence_rejected',
         'failed_activation_preserves_old', 'rollback_0', 'revocation_blocks_future_admission',
         'active_revocation_blocks_capture')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'fixture', 'launcher-build', 'program-build', 'runtime-build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--program-source-revision', required=True)
    parser.add_argument('--source-repository', type=Path, default=ROOT,
                        help='read-only Git object source; useful when SDK remapping hides worktree gitdir paths')
    parser.add_argument('--sdk-manifest-sha256', required=True)
    parser.add_argument('--sdk-tree-sha256', required=True)
    parser.add_argument('--repeat', type=int, choices=range(1, 9), default=3)
    args = parser.parse_args()
    system, system_source, fixture, launcher, program, runtime = (p.resolve(strict=True) for p in (
        args.system, args.system_source, args.fixture, args.launcher_build, args.program_build, args.runtime_build))
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    own_sources = {name: sha(ROOT / name) for name in (
        'tests/dynamic_generation_guest.py', 'tests/boot_smoke.py', 'tests/process_smoke.py',
        'tests/task_smoke.py', 'tests/shell_launch_support.py', 'scripts/build_dynamic_launcher.py',
        'scripts/make_work_disk.py', 'scripts/work_disk.py', 'scripts/sdk_receipt.py')}
    report = {'status': 'failed', 'runs': [], 'runner_sources': own_sources}
    guest = None
    try:
        native = bind_system(system, system_source)
        build = json.loads((fixture / 'receipt.json').read_bytes())
        approval = json.loads((launcher / 'receipt.json').read_bytes())
        staged = json.loads((program / 'manifest.json').read_bytes())
        roots = approval['approved_generations']
        if (build['status'] != 'built_not_run' or approval['status'] != 'built_not_run' or
                staged['status'] != 'built_not_run' or not staged.get('public_startup') or
                len(roots) != 3 or build['approved_generations'] != roots):
            raise ValueError('the native probe requires matching three-root builds and a real public GNU stage')
        if (approval['sdk_manifest_sha256'] != args.sdk_manifest_sha256 or
                approval['sdk_tree_sha256'] != args.sdk_tree_sha256 or
                build['sdk_manifest_sha256'] != args.sdk_manifest_sha256 or
                build['sdk_tree_sha256'] != args.sdk_tree_sha256):
            raise ValueError('independent SDK anchors differ')
        # Materialize the exact producer revision rather than substituting a
        # subsequently edited builder for the stage's source identities.
        repository = args.source_repository.resolve(strict=True)
        revision = subprocess.check_output(['git', 'rev-parse', args.program_source_revision + '^{commit}'],
                                           cwd=repository, text=True).strip()
        origins = [Path(name).parents[1] for name in staged['inputs']
                   if name.endswith('/scripts/build_dynamic_program.py')]
        if len(origins) != 1:
            raise ValueError('stage must bind exactly one program builder source')
        source_snapshot = out / 'program_source_snapshot'
        source_inputs = {}
        for name, digest in staged['inputs'].items():
            path = Path(name)
            if path.is_relative_to(origins[0]):
                relative = path.relative_to(origins[0]).as_posix()
                data = subprocess.check_output(['git', 'show', revision + ':' + relative], cwd=repository)
                destination = source_snapshot / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                destination.chmod(0o444)
                if sha(destination) != digest:
                    raise ValueError('materialized producer source differs: ' + relative)
                source_inputs[relative] = digest
            elif path != runtime / 'manifest.json' or sha(path) != digest:
                raise ValueError('unknown or changed external stage input: ' + name)
        frozen = {str(path): sha(path) for path in (
            system / 'manifest.json', fixture / 'receipt.json', launcher / 'receipt.json',
            program / 'manifest.json', runtime / 'manifest.json')}

        def verify_inputs():
            if bind_system(system, system_source) != native:
                raise ValueError('frozen system changed')
            sdk = verify_sdk(system / 'sdk', native)
            if sdk != approval['native_sdk_binding'] or sdk['tree_sha256'] != build['native_sdk_tree_sha256']:
                raise ValueError('native SDK differs from linked inputs')
            copied = tree_receipt(launcher / 'native_sdk_snapshot')
            if any(sdk[key] != value for key, value in copied.items()):
                raise ValueError('native SDK snapshot changed')
            c_binding = anchor_sdk(launcher / 'sdk_snapshot', args.sdk_manifest_sha256, args.sdk_tree_sha256)
            if c_binding != approval['c_sdk_binding'] or c_binding != staged['sdk_binding']:
                raise ValueError('complete C SDK differs from program or launcher binding')
            if sha(launcher / 'receipt.json') != build['launcher_receipt_sha256']:
                raise ValueError('probe linked a different approved header')
            for selected, directory in ((approval, launcher), (build, fixture)):
                for name, digest in selected['sources'].items():
                    if sha(relative_file(ROOT, name)) != digest:
                        raise ValueError('linked source changed: ' + name)
                for name, digest in selected['artifacts'].items():
                    if sha(relative_file(directory, name)) != digest:
                        raise ValueError('linked artifact changed: ' + name)
            for name, digest in source_inputs.items():
                if sha(relative_file(source_snapshot, name)) != digest:
                    raise ValueError('program source snapshot changed')
            for destination, item in staged['files'].items():
                guest_path(destination)
                if sha(relative_file(program, item['local'])) != item['sha256']:
                    raise ValueError('staged GNU object changed')
            generation = staged['generation']
            if (generation['id'] != roots[0]['id'] or generation['guest'] != roots[0]['manifest'] or
                    generation['sha256'] != roots[0]['sha256'] or
                    sha(relative_file(program, generation['local'])) != generation['sha256']):
                raise ValueError('staged generation differs from the approved root')
            for item in roots:
                guest_path(item['manifest']); guest_path(item['main'])
                if sha(relative_file(launcher, item['snapshot'])) != item['sha256']:
                    raise ValueError('approved generation snapshot changed')
            if any(sha(Path(path)) != digest for path, digest in frozen.items()):
                raise ValueError('an input receipt changed')
            if own_sources != {name: sha(ROOT / name) for name in own_sources}:
                raise ValueError('runner source changed')

        verify_inputs()
        installed = {destination: relative_file(program, item['local']) for destination, item in staged['files'].items()}
        if roots[1]['main'] in installed or roots[2]['main'] in installed:
            raise ValueError('fixture stage unexpectedly installs an alternate main')
        installed[roots[1]['main']] = installed[roots[0]['main']]
        for item in roots:
            if item['manifest'] in installed:
                raise ValueError('duplicate fixture path')
            installed[item['manifest']] = relative_file(launcher, item['snapshot'])
        installed['/bin/r2_probe.elf'] = fixture / 'dynamic_generation.elf'
        report.update(system_build_id=native['build_id'], iso_sha256=sha(system / 'xos-install.iso'),
                      native_sdk_tree_sha256=approval['native_sdk_binding']['tree_sha256'],
                      sdk_manifest_sha256=args.sdk_manifest_sha256, sdk_tree_sha256=args.sdk_tree_sha256,
                      input_receipts=frozen, program_source_revision=revision, program_sources=source_inputs,
                      approved_generations=roots,
                      installed_files={path: sha(local) for path, local in installed.items()},
                      deliberately_missing_main=roots[2]['main'])
        with tempfile.TemporaryDirectory(prefix='xos_generation_guest_') as temporary:
            disk = Path(temporary) / 'work.img'
            create_fat32(disk, 512)
            created = set()
            for destination, local in installed.items():
                for parent in reversed(Path(destination).parents):
                    if parent.as_posix() != '/' and parent.as_posix() not in created:
                        transfer(disk, 'mkdir', parent.as_posix()); created.add(parent.as_posix())
                transfer(disk, 'import', destination, local)
            guest = Guest(system / 'xos-install.iso', 'guest', iso=True, work_disk=disk,
                          qmp_enabled=False, log_dir=out)
            report['qemu_command'] = guest.command
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            pump(guest, 0.2)
            baseline = resources(guest)
            report['baseline'] = baseline
            for number in range(args.repeat):
                output = command(guest, 'exec-driver /bin/r2_probe.elf', b'kind=exited code=', timeout=180)
                (out / ('round_' + str(number) + '.log')).write_bytes(output)
                exits = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)', output)
                markers = re.findall(rb'R2_PROBE_PASS ([a-z0-9_]+)', output)
                if (markers != [name.encode() for name in CASES] or exits != [b'0'] or
                        output.count(b'P0_PUBLIC_C_OK constructor=1 tls=1 relocation=1 environment=1') != 4 or
                        output.count(b'R2_PROBE_OK cases=7 sequence=5 revoked=3') != 1 or b'R2_PROBE_FAIL' in output):
                    raise AssertionError(output[-8000:])
                actual = resources(guest)
                if actual != baseline:
                    raise AssertionError(f'resources {actual}, expected {baseline}')
                report['runs'].append({'round': number, 'status': 'passed', 'cases': list(CASES),
                                       'public_c_launches': 4, 'resources': actual})
            verify_inputs()
            report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS dynamic generation native guest:', len(report['runs']), 'rounds,', len(report['runs']) * len(CASES), 'cases')


if __name__ == '__main__':
    main()
