#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diagnose the READY fix by relinking copied GNU objects and running real guests.

This deliberately is not a new SDK producer or a replacement for the complete
public runtime qualification. Baseline archives remain unchanged; every changed
object, derivative generation and guest result receives an independent digest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from archive_member_map import read_archive
from boot_smoke import Guest
from dynamic_artifacts import generation_record
from glibc_g1_probe import clean_build_environment
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import inspect_sdk


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-build', 'runtime-source', 'system', 'system-source', 'sdk-build',
                 'c-stage', 'thread-stage', 'dash-receipt', 'dash-source', 'launcher-output', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('sdk-manifest-sha256', 'sdk-tree-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime, baseline = args.runtime_build.resolve(), args.runtime_source.resolve()
    report = {'status': 'failed', 'scope': 'diagnostic relink and constructor/thread regression only',
              'qualification_transfer': False, 'commands': [], 'inputs': {}, 'checks': []}
    inputs, guest = report['inputs'], None
    disk = out / 'work.img'
    env, removed = clean_build_environment(os.environ)
    env['LC_ALL'] = 'C'
    report['sanitized_environment'] = removed

    def bind(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = sha(path)
        if expected is not None and actual != expected:
            raise ValueError('digest mismatch: ' + str(path))
        if str(path) in inputs and inputs[str(path)] != actual:
            raise ValueError('input changed: ' + str(path))
        inputs[str(path)] = actual
        return actual

    def read(path):
        bind(path)
        return json.loads(Path(path).read_bytes())

    def run(name, argv, cwd=ROOT):
        argv = list(map(str, argv))
        executable = shutil.which(argv[0])
        if not executable:
            raise ValueError('missing executable: ' + argv[0])
        bind(executable)
        for argument in argv:
            if argument.startswith(str(runtime) + '/') and Path(argument).is_file():
                bind(argument)
        report['commands'].append({'name': name, 'argv': argv, 'cwd': str(cwd)})
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(argv, cwd=cwd, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)

    def bind_dependencies(path, cwd):
        text = Path(path).read_text().replace('\\\n', ' ').splitlines()[0]
        for item in shlex.split(text.split(':', 1)[1]):
            bind(cwd / item)

    def archive_replace(original, destination, replacements, ar):
        bind(original)
        old = read_archive(original)
        shutil.copyfile(original, destination)
        run(destination.stem + '-replace', [ar, 'rD', destination, *replacements.values()], out)
        new = read_archive(destination)
        if list(new) != list(old):
            raise ValueError('archive identity/order changed')
        for name, content in old.items():
            if new[name] != (replacements[name].read_bytes() if name in replacements else content):
                raise ValueError('unexpected archive change: ' + name)
        report.setdefault('archives', {})[destination.name] = {
            'members': len(old), 'replaced': sorted(replacements), 'sha256': sha(destination)}

    try:
        bind(__file__)
        system = bind_system(args.system, args.system_source)
        bind(args.system / 'manifest.json')
        binding = inspect_sdk('glibc', args.sdk_build)['binding']
        if (binding['sdk_manifest_sha256'] != args.sdk_manifest_sha256
                or binding['sdk_tree_sha256'] != args.sdk_tree_sha256):
            raise ValueError('independent SDK anchors differ')
        metadata = read(runtime / 'manifest.json')
        if metadata['status'] != 'public_runtime_built_not_run' or metadata['sdk_binding'] != binding:
            raise ValueError('completed baseline public GNU producer required')
        for group in ('recipe_inputs', 'port_inputs', 'native_inputs'):
            for name, expected in metadata[group].items():
                bind(baseline / name, expected)
        for name, expected in metadata['artifacts'].items():
            bind(runtime / name, expected)
        for tool in metadata['tools'].values():
            bind(tool['path'], tool['sha256'])
        tools = {name: value['path'] for name, value in metadata['tools'].items()}
        upstream = runtime / metadata['source']
        log = runtime / 'build-public-runtime.log'
        bind(log)
        lines = log.read_text().replace('\\\n', ' ').splitlines()

        def recorded(output):
            expression = r'\s-o\s+' + re.escape(str(output)) + r'(?:\s|$)'
            selected = [line for line in lines if re.search(expression, line)]
            if len(selected) != 1:
                raise ValueError('original command is not unique: ' + str(output))
            return shlex.split(selected[0])

        sources = out / 'source'
        for name in ('csu/libc-start.c', 'elf/dl-init.c'):
            target = sources / name
            target.parent.mkdir(parents=True, exist_ok=True)
            bind(upstream / name)
            shutil.copyfile(upstream / name, target)
        old_patch = baseline / 'src/ports/glibc/patches/0041-xos-public-runtime-ready.patch'
        new_patch = ROOT / 'src/ports/glibc/patches/0041-xos-public-runtime-ready.patch'
        bind(old_patch)
        bind(new_patch)
        run('remove-old-rtld-ready', ['patch', '--batch', '--fuzz=0', '-R', '-p1', '-i', old_patch], sources)
        run('apply-libc-entry-ready', ['patch', '--batch', '--fuzz=0', '-p1', '-i', new_patch], sources)
        for name in ('csu/libc-start', 'elf/dl-init'):
            old = runtime / ('gnu/' + name + '.os')
            new = out / (Path(name).name + '.os')
            replacements = {str(old): str(new), str(old) + '.dt': str(new) + '.dt'}
            argv = [replacements.get(arg, arg) for arg in recorded(old)]
            if name.startswith('csu/'):
                argv[1:1] = ['-I', str(sources)]
            else:
                argv[argv.index('dl-init.c')] = str(sources / 'elf/dl-init.c')
            cwd = upstream / Path(name).parent
            run('compile-' + Path(name).name, argv, cwd)
            bind_dependencies(str(new) + '.dt', cwd)

        native_replacements = {}
        for name in ('spawn', 'rtld_control'):
            source = ROOT / ('src/user/loader/dynamic/' + name + '.cpp')
            bind(source)
            entries = [step['command'] for step in metadata['steps']
                       if step['name'].startswith('native-compile-')
                       and any(arg.endswith('/dynamic/' + name + '.cpp') for arg in step['command'])]
            if len(entries) != 1:
                raise ValueError('native compiler record missing')
            argv = entries[0].copy()
            old = Path(argv[argv.index('-o') + 1])
            new = out / old.name
            argv = [str(new) if arg == str(old) else str(new) + '.d' if arg == str(old) + '.d'
                    else str(source) if arg.endswith('/dynamic/' + name + '.cpp') else arg for arg in argv]
            run('compile-native-' + name, argv)
            bind_dependencies(str(new) + '.d', ROOT)
            native_replacements[old.name] = new
        native_archive = out / 'libxos_terminal_pic.a'
        archive_replace(runtime / 'native_pic/libxos_terminal_pic.a', native_archive, native_replacements, tools['ar'])
        libc_archive = out / 'libc_pic.a'
        archive_replace(runtime / 'gnu/libc_pic.a', libc_archive, {'libc-start.os': out / 'libc-start.os'}, tools['ar'])

        rewrites = {str(runtime / 'gnu/elf/dl-init.os'): str(out / 'dl-init.os'),
                    str(runtime / 'gnu/libc_pic.a'): str(libc_archive),
                    str(runtime / 'native_pic/libxos_terminal_pic.a'): str(native_archive)}
        rewrites.update({str(runtime / 'native_pic' / name): str(path) for name, path in native_replacements.items()})
        for old_name, new_name, cwd in (
                ('gnu/elf/dl-allobjs.os', 'dl-allobjs.os', upstream / 'elf'),
                ('gnu/elf/librtld.os', 'librtld.os', upstream / 'elf'),
                ('gnu/elf/ld.so.new', 'ld.so', upstream / 'elf'),
                ('gnu/libc_pic.os', 'libc_pic.os', upstream)):
            old, new = runtime / old_name, out / new_name
            rewrites[str(old)] = str(new)
            argv = [rewrites.get(arg, str(out / 'librtld.os.map') if arg ==
                    '-Wl,-Map,' + str(runtime / 'gnu/elf/librtld.os.map') else arg) for arg in recorded(old)]
            argv = ['-Wl,-Map,' + str(out / 'librtld.os.map') if arg == str(out / 'librtld.os.map') else arg for arg in argv]
            run('link-' + new_name, argv, cwd)
        run('clean-libc-stubs', [tools['objcopy'], '@' + str(runtime / 'gnu/libc_pic.opts'),
                                out / 'libc_pic.os', out / 'libc_pic.os.clean'], upstream)
        rewrites[str(runtime / 'gnu/libc_pic.os.clean')] = str(out / 'libc_pic.os.clean')
        rewrites[str(runtime / 'gnu/elf/ld.so')] = str(out / 'ld.so')
        rewrites[str(runtime / 'gnu/libc.so')] = str(out / 'libc.so')
        run('link-libc', [rewrites.get(arg, arg) for arg in recorded(runtime / 'gnu/libc.so')], upstream)
        report['runtime_derivative'] = {name: sha(out / name) for name in ('libc.so', 'ld.so')}

        files, generations = {}, []
        for original, source, slot in (
                (args.c_stage, ROOT / 'tests/fixtures/public_runtime/application.c', 0),
                (args.thread_stage, ROOT / 'tests/fixtures/glibc_d1/shared_std_thread_application.cpp', 1)):
            stage = read(original / 'manifest.json')
            if stage['sdk_binding'] != binding or stage['native_abi'] != metadata['native_abi']:
                raise ValueError('baseline stage belongs to another runtime')
            for path, expected in stage['inputs'].items():
                bind(path, expected)
            dest = out / stage['name']
            payload = dest / 'payload'
            payload.mkdir(parents=True)
            for item in stage['files'].values():
                old = original / item['local']
                bind(old, item['sha256'])
                shutil.copyfile(old, payload / old.name)
            (payload / 'ld.so.1').symlink_to('ld_xos_x86_64.so.1')
            for input_name, output_name in (('libc.so', 'libc.so.0.1'), ('ld.so', 'ld_xos_x86_64.so.1')):
                run(stage['name'] + '-strip-' + input_name,
                    [tools['objcopy'], '--strip-debug', out / input_name, payload / output_name])
            bind(source)
            main_object = dest / 'main.o'
            argv = stage['commands']['compile-main'].copy()
            argv[argv.index('-c') + 1] = str(source)
            argv[argv.index('-o') + 1] = str(main_object)
            run(stage['name'] + '-compile-main', argv)
            replacements = {str(original / 'payload'): str(payload), str(original / 'main.o'): str(main_object)}
            replacements.update({str(original / item['local']): str(payload / Path(item['local']).name)
                                 for item in stage['files'].values()})
            run(stage['name'] + '-link-main', [replacements.get(arg, arg) for arg in stage['commands']['link-main']])
            entries = [(payload / Path(item['local']).name, path) for path, item in stage['files'].items()]
            data, _ = generation_record(stage['generation_id'], args.sdk_manifest_sha256,
                                        metadata['native_abi'], entries)
            generation = dest / 'generation.bin'
            generation.write_bytes(data)
            run(stage['name'] + '-preflight', [original / 'preflight', generation, *(local for local, _ in entries)])
            generations.append((generation, stage['generation']['guest']))
            for local, path in [*entries, (generation, stage['generation']['guest'])]:
                if path in files and sha(files[path]) != sha(local):
                    raise ValueError('conflicting derivative closure path')
                files[path] = local
        launcher = args.launcher_output.resolve()
        argv = [sys.executable, args.system_source / 'scripts/build_dynamic_launcher.py',
                '--system', args.system, '--system-source', args.system_source, '--sdk-build', args.sdk_build,
                '--sdk-manifest-sha256', args.sdk_manifest_sha256, '--sdk-tree-sha256', args.sdk_tree_sha256,
                '--output', launcher]
        for local, path in generations:
            argv.extend(['--generation', local, path])
        run('build-diagnostic-launcher', argv)
        receipt = read(launcher / 'receipt.json')
        bind(launcher / 'dynamic-run.elf', receipt['artifacts']['dynamic-run.elf'])
        files['/usr/bin/dynamic-run'] = launcher / 'dynamic-run.elf'
        dash = read(args.dash_receipt)
        dash_elf = args.dash_source / dash['elf']
        bind(dash_elf, dash['sha256'])
        files['/usr/bin/dash'] = dash_elf
        (out / 'input.txt').write_bytes(b'ABCDEFGH\n')
        files['/tests/input'] = out / 'input.txt'
        (out / 'spawn.sh').write_text('export DYNAMIC_ENV=verified\n/usr/bin/dynamic-run 0 /apps/p0c/main spawn\n')
        files['/tests/spawn.sh'] = out / 'spawn.sh'
        (out / 'thread.sh').write_text('/usr/bin/dynamic-run 1 /apps/p0thread/main\n')
        files['/tests/thread.sh'] = out / 'thread.sh'
        report['installed'] = {path: {'local': str(local), 'sha256': sha(local)} for path, local in files.items()}
        for local in files.values():
            bind(local)
        create_fat32(disk, 512)
        parents = sorted({str(p) for name in files for p in Path(name).parents if str(p) != '/'},
                         key=lambda name: (name.count('/'), name))
        for name in parents:
            transfer(disk, 'mkdir', name)
        for path, local in files.items():
            transfer(disk, 'import', path, local)
        guest = Guest(args.system / 'xos-install.iso', 'ready_regression', work_disk=disk,
                      iso=True, qmp_enabled=False, log_dir=out)
        report['qemu_command'] = guest.command
        report['native_build_id'] = system['build_id']
        bind(guest.command[0])
        guest.expect(b'xos64> ', timeout=40)
        send_bytes(guest, b'run\r')
        guest.expect_supervisor(trace=True, timeout=40)
        command(guest, 'demo quiet', b'demo tasks ')
        report['baseline_resources'] = resources(guest)
        thread_markers = ('P0_PUBLIC_CONSTRUCTOR_THREAD_OK', 'D2_STD_THREAD_APP_TLS_DTOR',
                          'D2_SHARED_CXX_TLS_DTOR', 'D2_STD_THREAD_OK move=joined app-dtor=1 dso-dtor=1 tls=isolated')
        for name, line, markers in (
                ('constructor-spawn', 'dash /tests/spawn.sh', ('P0_PUBLIC_READY_AFTER_CONSTRUCTORS',
                 'P0_PUBLIC_SPAWN_CHILD_OK aliases=1 cloexec=1',
                 'P0_PUBLIC_SPAWN_OK ordinary_api=1 shared_cursor=1 wait_ready=1')),
                ('constructor-thread-xsh', 'dynamic-run 1 /apps/p0thread/main', thread_markers),
                ('constructor-thread-dash', 'dash /tests/thread.sh', thread_markers)):
            row = {'name': name, 'status': 'failed', 'resources_before': resources(guest)}
            report['checks'].append(row)
            started = time.monotonic()
            output = command(guest, line, b'xsh> ', timeout=120)
            row.update(seconds=round(time.monotonic() - started, 3), output=output.decode(errors='replace'))
            if any(marker.encode() not in output.splitlines() for marker in markers):
                raise AssertionError(name + ' missing required result: ' + repr(output[-4000:]))
            statuses = re.findall(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)(?:\r?\n|$)', output)
            if not statuses or statuses[-1] != b'0' or not re.search(
                    rb'DYNAMIC_RUN_EXIT slot=\d+ generation=\d+ pid=\d+ outcome=1 code=0\r?\n', output):
                raise AssertionError(name + ' failed completion')
            row['resources_after'] = resources(guest)
            if row['resources_before'] != row['resources_after'] or row['resources_after'] != report['baseline_resources']:
                raise AssertionError(name + ' did not reclaim resources exactly')
            row['status'] = 'passed'
            print('PASS', name, row['seconds'], flush=True)
        for path, expected in inputs.items():
            if sha(path) != expected:
                raise ValueError('bound input changed during diagnostic: ' + path)
        if bind_system(args.system, args.system_source) != system:
            raise ValueError('system changed during diagnostic')
        report['status'] = 'passed'
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        if disk.exists():
            report['work_disk_after_sha256'] = sha(disk)
            disk.unlink()
        report['artifacts'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                               if p.is_file() and p.name != 'report.json'}
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
