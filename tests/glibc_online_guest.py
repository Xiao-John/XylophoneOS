#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the explicit online GNU profile with actual native concurrent threads."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from build_dynamic_program import inspect_native_sdk
from dynamic_artifacts import generation_record
from make_work_disk import create_fat32
from process_smoke import command, resources
from sdk_receipt import verify_sdk
from shell_launch_support import bind_system, check_hash, relative_file, sha
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk

CASES = ('dependencies', 'namespaces', 'tls', 'lazy_tls', 'pthread_exit', 'last_worker',
         'concurrent', 'pin_replacement', 'rejections', 'cycles')


def mutation_input(source):
    """Locate file-backed ELF metadata in an already verified target fixture."""
    data = bytearray(source.read_bytes())
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phnum = struct.unpack_from('<H', data, 56)[0]
    programs = [struct.unpack_from('<IIQQQQQQ', data, phoff + 56 * i) for i in range(phnum)]

    def offset(address, size):
        for item in programs:
            if item[0] == 1 and item[3] <= address and address + size <= item[3] + item[5]:
                return item[2] + address - item[3]
        raise ValueError('version metadata is outside a file-backed load')

    tags = {}
    for item in programs:
        if item[0] == 2:
            for at in range(item[2], item[2] + item[5], 16):
                tag, value = struct.unpack_from('<QQ', data, at)
                if not tag:
                    break
                tags[tag] = value
    return data, programs, tags, offset


def wrong_provider_version(source, destination):
    """Keep a well-formed version requirement whose provider cannot satisfy it."""
    data, _, tags, offset = mutation_input(source)
    # Different providers can share one version-name string in .dynstr. Keep
    # every Vernaux hash consistent with that string so this remains a valid
    # ELF whose provider closure is unsatisfied, rather than malformed input.
    auxiliaries = []
    need_address = tags[0x6ffffffe]
    for _ in range(tags[0x6fffffff]):
        need = offset(need_address, 16)
        count = struct.unpack_from('<H', data, need + 2)[0]
        auxiliary_address = need_address + struct.unpack_from('<I', data, need + 8)[0]
        for _ in range(count):
            auxiliary = offset(auxiliary_address, 16)
            auxiliaries.append(auxiliary)
            auxiliary_address += struct.unpack_from('<I', data, auxiliary + 12)[0]
        need_address += struct.unpack_from('<I', data, need + 12)[0]
    if not auxiliaries:
        raise ValueError('version fixture has no provider requirements')
    name_offset = struct.unpack_from('<I', data, auxiliaries[0] + 8)[0]
    name = offset(tags[5] + name_offset, 1)
    end = data.index(0, name)
    original = bytes(data[name:end]).decode('ascii')
    if not original or original.startswith('Z'):
        raise ValueError('unexpected provider version fixture')
    data[name] = ord('Z')
    value = 0
    for byte in data[name:end]:
        value = (value << 4) + byte
        high = value & 0xf0000000
        if high:
            value ^= high >> 24
        value &= ~high
    updated = 0
    for auxiliary in auxiliaries:
        if struct.unpack_from('<I', data, auxiliary + 8)[0] == name_offset:
            struct.pack_into('<I', data, auxiliary, value)
            updated += 1
    destination.write_bytes(data)
    return {'original': original, 'required': bytes(data[name:end]).decode('ascii'),
            'updated_requirements': updated,
            'original_sha256': sha(source), 'modified_sha256': sha(destination)}


def rejected_tls_relocation(source, destination, kind):
    """Change a real global-dynamic TLS relocation, preserving ELF geometry."""
    data, programs, tags, offset = mutation_input(source)
    if kind not in (18, 36) or tags[9] != 24:
        raise ValueError('unexpected TLS relocation fixture')
    for entry in range(0, tags[8], 24):
        at = offset(tags[7] + entry, 24)
        address, info = struct.unpack_from('<QQ', data, at)
        if info & 0xffffffff != 16:
            continue
        if not any(item[0] == 1 and item[1] & 2 and item[3] <= address
                   and address + 16 <= item[3] + item[6] for item in programs):
            raise ValueError('TLS relocation must have an existing writable 16-byte slot')
        struct.pack_into('<Q', data, at + 8, (info & ~0xffffffff) | kind)
        destination.write_bytes(data)
        return {'original_kind': 16, 'rejected_kind': kind, 'target': address,
                'original_sha256': sha(source), 'modified_sha256': sha(destination)}
    raise ValueError('expected real DTPMOD64 relocation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'system-source', 'runtime-build', 'runtime-source', 'unwinder-build',
                 'launcher-build', 'launcher-source', 'stage', 'fixed-stage', 'fixed-launcher', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--case', action='append', choices=CASES)
    args = parser.parse_args()
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'scope': 'explicit approved online GNU profile; C callers with real pthread unwinding',
              'inputs': {}, 'checks': [], 'not_run': ['C++ online libraries', 'SMP', 'physical hardware']}
    inputs = report['inputs']
    guest = None

    def save():
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = sha(path)
        if expected is not None and expected != actual:
            raise ValueError('bound input differs: ' + str(path))
        if str(path) in inputs and inputs[str(path)] != actual:
            raise ValueError('input changed while binding: ' + str(path))
        inputs[str(path)] = actual
        return actual

    def read(path):
        bind(path)
        return json.loads(Path(path).read_bytes())

    def verify_all():
        for path, expected in inputs.items():
            check_hash(Path(path), expected, 'bound online input')
        if bind_system(args.system, args.system_source) != system:
            raise ValueError('system source/artifacts changed')
        if inspect_native_sdk(args.system / 'sdk') != native_binding:
            raise ValueError('native SDK changed')
        if inspect_sdk('glibc', args.runtime_build / 'sdk_snapshot')['binding'] != c_binding:
            raise ValueError('complete C SDK snapshot changed')

    def launcher_binding(directory):
        value = read(directory / 'receipt.json')
        if (value.get('status') != 'built_not_run' or value['c_sdk_binding'] != c_binding
                or value['native_sdk_binding'] != native_receipt
                or value['native_system_build_id'] != system['build_id']
                or len(value['approved_generations']) != 1):
            raise ValueError('controller is not this exact one-root composition')
        bind(args.system / 'manifest.json', value['native_system_manifest_sha256'])
        for name, expected in value['sources'].items():
            bind(relative_file(args.launcher_source, name), expected)
        for name, expected in value['artifacts'].items():
            bind(relative_file(directory, name), expected)
        if (inspect_sdk('glibc', directory / 'sdk_snapshot')['binding'] != c_binding
                or verify_sdk(directory / 'native_sdk_snapshot', system) != native_receipt):
            raise ValueError('controller SDK copies differ')
        root = value['approved_generations'][0]
        bind(relative_file(directory, root['snapshot']), root['sha256'])
        return value

    def stage_binding(directory, controller, online):
        stage = read(directory / 'manifest.json')
        if (stage.get('status') != 'built_not_run' or not stage.get('public_startup')
                or stage['native_abi'] != runtime['native_abi'] or stage['sdk_binding'] != c_binding
                or stage['native_sdk_binding'] != native_binding
                or bool(stage.get('online_libraries')) != online):
            raise ValueError('program is not the selected online/startup-only composition')
        for path, expected in stage['inputs'].items():
            bind(path, expected)
        if inspect_native_sdk(directory / 'native_sdk_snapshot') != native_binding:
            raise ValueError('program native SDK copy differs')
        generation = stage['generation']
        approved = controller['approved_generations'][0]
        if any(generation[key] != approved[other] for key, other in
               (('id', 'id'), ('sha256', 'sha256'), ('guest', 'manifest'))):
            raise ValueError('program is not explicitly approved by this controller')
        files = {}
        for path, item in stage['files'].items():
            if (not re.fullmatch(r'/[A-Za-z0-9_./+\-]+', path)
                    or any(part in ('', '.', '..') for part in path[1:].split('/'))):
                raise ValueError('noncanonical guest path')
            source = relative_file(directory, item['local'])
            bind(source, item['sha256'])
            files[path] = source
        source = relative_file(directory, generation['local'])
        bind(source, generation['sha256'])
        files[generation['guest']] = source
        return stage, files

    def boot(name, files, definitions, *, failure=False):
        nonlocal guest
        directory = out / name
        directory.mkdir()
        disk = directory / 'work.img'
        row = {'name': name, 'status': 'failed', 'installed': {path: sha(local) for path, local in files.items()}}
        report['checks'].append(row)
        try:
            create_fat32(disk, 512)
            parents = sorted({str(parent) for path in files for parent in Path(path).parents
                              if str(parent) != '/'}, key=lambda path: (path.count('/'), path))
            for path in parents:
                transfer(disk, 'mkdir', path)
            for path, source in files.items():
                transfer(disk, 'import', path, source)
            verify_all()
            row['disk_before_sha256'] = sha(disk)
            guest = Guest(args.system / 'xos-install.iso', name, work_disk=disk,
                          iso=True, qmp_enabled=False, log_dir=directory)
            row['qemu_command'] = guest.command
            row['qemu_version'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            bind(guest.command[0])
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            command(guest, 'audio stop', b'xsh> ')
            baseline = resources(guest)
            row['baseline'] = baseline
            row['cases'] = []
            for case, line, marker in definitions:
                before = resources(guest)
                started = time.monotonic()
                output = command(guest, line, b'xsh> ', timeout=150)
                item = {'name': case, 'seconds': round(time.monotonic() - started, 3),
                        'output': output.decode(errors='replace'), 'resources_before': before}
                row['cases'].append(item)
                complete = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)(?:\r?\n|$)', output)
                if failure:
                    if (not complete or complete[-1] != b'126' or marker not in output
                            or b'K3_PASS' in output or b'K3_FAIL' in output or b'DYNAMIC_RUN_EXIT' in output):
                        raise AssertionError('invalid approved object did not fail before program use: ' + repr(output))
                elif (marker not in output.splitlines() or not complete or complete[-1] != b'0'
                      or not re.search(rb'DYNAMIC_RUN_EXIT slot=0 generation=\d+ pid=\d+ outcome=1 code=0\r?\n', output)):
                    raise AssertionError('missing exact successful online case: ' + repr(output))
                after = resources(guest)
                item['resources_after'] = after
                if before != after or after != baseline:
                    raise AssertionError('native pages/processes/completions did not return exactly')
                item['status'] = 'passed'
                save()
                print('PASS', name, case, item['seconds'], flush=True)
            verify_all()
            row['status'] = 'passed'
        finally:
            if guest:
                guest.close()
                guest = None
            if disk.exists():
                row['disk_after_sha256'] = sha(disk)
                disk.unlink()
            save()

    try:
        for relative in ('tests/glibc_online_guest.py', 'tests/boot_smoke.py', 'tests/process_smoke.py',
                         'tests/task_smoke.py', 'tests/shell_launch_support.py', 'scripts/make_work_disk.py',
                         'scripts/work_disk.py', 'scripts/run_qemu.py', 'scripts/build_dynamic_program.py',
                         'scripts/build_dynamic_launcher.py', 'scripts/dynamic_artifacts.py',
                         'scripts/xypm_sdk_profile.py', 'scripts/sdk_receipt.py'):
            bind(ROOT / relative)
        system = bind_system(args.system, args.system_source)
        bind(args.system / 'manifest.json')
        native_binding = inspect_native_sdk(args.system / 'sdk')
        native_receipt = verify_sdk(args.system / 'sdk', system)
        runtime = read(args.runtime_build / 'manifest.json')
        if (runtime.get('status') != 'public_runtime_built_not_run' or not runtime.get('public_startup')
                or not runtime.get('online_libraries')):
            raise ValueError('explicit online runtime required')
        for group in ('recipe_inputs', 'port_inputs', 'native_inputs'):
            for name, expected in runtime[group].items():
                bind(relative_file(args.runtime_source, name), expected)
        for name, expected in runtime['artifacts'].items():
            bind(relative_file(args.runtime_build, name), expected)
        c_binding = inspect_sdk('glibc', args.runtime_build / 'sdk_snapshot')['binding']
        if (c_binding != runtime['sdk_binding']
                or c_binding['sdk_manifest_sha256'] != runtime['expected_sdk_manifest_sha256']
                or c_binding['sdk_tree_sha256'] != runtime['expected_sdk_tree_sha256']):
            raise ValueError('independent complete C SDK anchors differ')
        shared = read(args.unwinder_build / 'manifest.json')
        if (shared.get('status') != 'built_not_run' or shared.get('scope') != 'public_native_unwinder_only'
                or not shared.get('public_startup') or shared['native_abi'] != runtime['native_abi']
                or shared['public_runtime_manifest_sha256'] != sha(args.runtime_build / 'manifest.json')):
            raise ValueError('real pthread tests require the exact matched native unwinder')
        for path, expected in shared['bound_inputs'].items():
            bind(path, expected)
        for name, expected in shared['recipe_inputs'].items():
            bind(relative_file(args.runtime_source, name), expected)
        for name, expected in shared['artifacts'].items():
            bind(relative_file(args.unwinder_build / 'lib', name), expected)
        approval = launcher_binding(args.launcher_build)
        stage, files = stage_binding(args.stage, approval, True)
        files['/usr/bin/dynamic-run'] = args.launcher_build / 'dynamic-run.elf'
        main_path = approval['approved_generations'][0]['main']
        report.update(system_build_id=system['build_id'], native_abi=runtime['native_abi'],
                      native_sdk_binding=native_binding, c_sdk_binding=c_binding)
        definitions = [(name, 'dynamic-run 0 ' + main_path + ' ' + name,
                        ('K3_LAST_THREAD_COMPLETE' if name == 'last_worker' else 'K3_PASS ' + name).encode())
                       for name in (args.case or CASES)]
        boot('online', files, definitions)

        fixed_approval = launcher_binding(args.fixed_launcher)
        _, fixed_files = stage_binding(args.fixed_stage, fixed_approval, False)
        fixed_files['/usr/bin/dynamic-run'] = args.fixed_launcher / 'dynamic-run.elf'
        boot('startup_only', fixed_files, [('fixed', 'dynamic-run 0 '
             + fixed_approval['approved_generations'][0]['main'] + ' fixed', b'K3_PASS fixed')])

        missing = dict(files)
        del missing['/apps/p1online/libonline_tls.so']
        boot('missing_object', missing, [('missing_object', 'dynamic-run 0 ' + main_path + ' dependencies',
                                         b'dynamic-run: approved policy error=1')], failure=True)
        corrupt = out / 'wrong_object.so'
        corrupt.write_bytes(b'unapproved object substituted at an approved pathname\n')
        bind(corrupt)
        replaced = dict(files)
        replaced['/apps/p1online/libonline_tls.so'] = corrupt
        boot('new_object', replaced, [('new_object', 'dynamic-run 0 ' + main_path + ' dependencies',
                                      b'dynamic-run: approved policy error=')], failure=True)

        report['negative_objects'] = []
        for negative_index, (name, kind, expected_error) in enumerate(
                (('wrong_version', None, 13), ('static_tls', 18, 3), ('tlsdesc', 36, 3)), 1):
            bad_object = out / (name + '.so')
            source = files['/apps/p1online/libonline_tls.so']
            mutation = (wrong_provider_version(source, bad_object) if kind is None
                        else rejected_tls_relocation(source, bad_object, kind))
            bind(bad_object)
            entries = [(bad_object if path == '/apps/p1online/libonline_tls.so'
                        else relative_file(args.stage, item['local']), path) for path, item in stage['files'].items()]
            generation, _ = generation_record(stage['generation']['id'] + negative_index,
                c_binding['sdk_manifest_sha256'], runtime['native_abi'], entries,
                online_sonames=[item['soname'] for item in stage['online_libraries']['libraries']])
            generation_file = out / (name + '.bin')
            generation_file.write_bytes(generation)
            bind(generation_file)
            preflight = args.stage / 'preflight'
            bind(preflight)
            preflight_command = [str(preflight), str(generation_file), *(str(local) for local, _ in entries)]
            result = subprocess.run(preflight_command, capture_output=True, text=True, timeout=30)
            output = result.stdout + result.stderr
            (out / (name + '_preflight.log')).write_text(output)
            row = {'name': name, 'mutation': mutation, 'preflight_command': preflight_command,
                   'returncode': result.returncode, 'output': output}
            report['negative_objects'].append(row)
            objects = re.findall(r'^DYNAMIC_PREFLIGHT object=(\d+) error=(\d+) ', output, re.MULTILINE)
            if kind is None:
                valid = (result.returncode == 68 and len(objects) == len(entries)
                         and all(int(index) == i and error == '0' for i, (index, error) in enumerate(objects))
                         and output.splitlines()[-1:] == ['DYNAMIC_PREFLIGHT closure=13'])
            else:
                rejected_index = next(i for i, (_, path) in enumerate(entries)
                                      if path == '/apps/p1online/libonline_tls.so')
                valid = (result.returncode == 67 and len(objects) == rejected_index + 1
                         and all(int(index) == i and error == ('3' if i == rejected_index else '0')
                                 for i, (index, error) in enumerate(objects)))
            if not valid:
                raise ValueError(name + ' negative did not reach its intended production verifier rejection')
            generation_path = '/usr/lib/xos/generations/online_' + name + '.bin'
            negative_launcher = out / (name + '_launcher')
            invocation = [sys.executable, str(ROOT / 'scripts/build_dynamic_launcher.py'),
                '--system', str(args.system), '--system-source', str(args.system_source),
                '--sdk-build', str(args.runtime_build / 'sdk_snapshot'),
                '--sdk-manifest-sha256', c_binding['sdk_manifest_sha256'],
                '--sdk-tree-sha256', c_binding['sdk_tree_sha256'], '--output', str(negative_launcher),
                '--generation', str(generation_file), generation_path]
            with (out / (name + '_launcher_build.log')).open('w') as log:
                subprocess.run(invocation, stdout=log, stderr=subprocess.STDOUT, check=True)
            row['launcher_command'] = invocation
            launcher_binding(negative_launcher)
            rejected_files = dict(files)
            rejected_files['/apps/p1online/libonline_tls.so'] = bad_object
            del rejected_files[stage['generation']['guest']]
            rejected_files[generation_path] = generation_file
            rejected_files['/usr/bin/dynamic-run'] = negative_launcher / 'dynamic-run.elf'
            boot(name, rejected_files, [(name, 'dynamic-run 0 ' + main_path + ' dependencies',
                 ('dynamic-run: approved policy error=' + str(expected_error)).encode())], failure=True)
        verify_all()
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        save()
        evidence = {str(path.relative_to(out)): sha(path) for path in sorted(out.rglob('*'))
                    if path.is_file() and path.name != 'evidence_manifest.json'}
        (out / 'evidence_manifest.json').write_text(json.dumps({'status': report['status'], 'files': evidence}, indent=2) + '\n')


if __name__ == '__main__':
    main()
