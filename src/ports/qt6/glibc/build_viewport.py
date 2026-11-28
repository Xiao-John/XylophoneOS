#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build locked QtBase host generators or the matched XOS glibc raster viewport."""
import argparse
from hashlib import file_digest
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PORT = Path(__file__).resolve().parent
QT = PORT.parent
ROOT = QT.parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import metadata_snapshot, verify_profile


def digest(path):
    with path.open('rb') as stream: return file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='store_true')
    for name in ('archive', 'output'):
        parser.add_argument('--' + name, required=True, type=lambda value: Path(value).resolve())
    for name in ('sdk-build', 'sdk-profile', 'host-qt'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve())
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if args.output.exists(): parser.error('select a fresh output directory')
    if not args.host and not all((args.sdk_build, args.sdk_profile, args.host_qt)):
        parser.error('target viewport requires --sdk-build, --sdk-profile and --host-qt')
    lock_path = QT / 'source_lock.json'
    lock = json.loads(lock_path.read_bytes())
    if digest(args.archive) != lock['sha256']: parser.error('QtBase archive differs from its lock')
    env, removed = clean_build_environment(os.environ)
    for key in ('CMAKE_PREFIX_PATH', 'Qt6_DIR', 'Qt6_ROOT', 'QT_ADDITIONAL_PACKAGES_PREFIX_PATH',
                'QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH'): env.pop(key, None)
    env['LC_ALL'] = 'C'
    out = args.output; out.mkdir(parents=True)
    source, build, prefix = out / 'source', out / 'build', out / 'prefix'
    inputs = {args.archive: lock['sha256'], lock_path: digest(lock_path), Path(__file__): digest(Path(__file__))}
    report = {'status': 'building', 'steps': [], 'sanitized_environment': removed,
              'qtbase_archive_sha256': lock['sha256'], 'guest_qualification': 'not_run'}

    def save(): (out / 'build_record.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')

    def run(stage, command, cwd=ROOT):
        command = list(map(str, command)); log = out / (stage + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
        report['steps'].append({'stage': stage, 'command': command, 'returncode': result.returncode, 'log_sha256': digest(log)})
        save()
        if result.returncode: raise RuntimeError(stage + ' failed; see ' + str(log))

    save()
    try:
        configure = ['cmake', '-S', source, '-B', build, '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_INSTALL_PREFIX=' + str(prefix), '-DBUILD_SHARED_LIBS=OFF', '-DQT_BUILD_EXAMPLES=OFF',
            '-DQT_BUILD_TESTS=OFF', '-DQT_BUILD_BENCHMARKS=OFF']
        if args.host:
            spec = importlib.util.spec_from_file_location('qt_host_source', QT / 'qml/build_host.py')
            helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
            inputs[QT / 'qml/build_host.py'] = digest(QT / 'qml/build_host.py')
            with args.archive.open('rb') as stream:
                helper.extract_source(stream, 'qtbase-everywhere-src-' + lock['version'], source)
            off = ('gui', 'widgets', 'network', 'opengl', 'sql', 'dbus', 'concurrent', 'testlib',
                   'icu', 'framework', 'system_pcre2', 'system_zlib')
        else:
            preparation = [*sorted((QT / 'patches').glob('*.patch')), *sorted((QT / 'mkspecs/xos-g++').rglob('*'))]
            preparation += [QT / 'runtime' / name for name in ('qeventdispatcher_xos.cpp',
                'qeventdispatcher_xos_p.h', 'wake_gate.hpp', 'qmutex_xos.cpp', 'unsupported_posix.cpp')]
            preparation += sorted((ROOT / 'src/shared/include/xos').glob('*.hpp'))
            preparation += sorted((ROOT / 'src/user/include/xos').glob('*.hpp'))
            inputs.update({path: digest(path) for path in preparation if path.is_file()})
            profile, profile_hash = metadata_snapshot(args.sdk_profile)
            binding = verify_profile(profile, 'glibc', args.sdk_build)
            if not {'cxx_runtime', 'threads'} <= set(profile['features']):
                raise ValueError('viewport requires the complete C++/pthread SDK')
            manifest, manifest_hash = metadata_snapshot(args.sdk_build / 'manifest.json', profile['sdk_binding']['sdk_manifest_sha256'])
            tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib')}
            for name, tool in tools.items():
                if tool.get('sha256') != manifest['tools']['x86_64-elf-' + name]['sha256']:
                    raise ValueError('target tool differs from SDK: ' + name)
            host, host_hash = metadata_snapshot(args.host_qt.parent / 'manifest.json')
            if host['status'] != 'qtbase_host_installed' or host['qtbase_archive_sha256'] != lock['sha256']:
                raise ValueError('host Qt build does not match the source lock')
            inputs[args.host_qt.parent / 'manifest.json'] = host_hash
            for name, expected in host['artifacts'].items(): inputs[args.host_qt / name] = expected
            for name in ('moc', 'rcc'):
                version = subprocess.check_output([args.host_qt / 'libexec' / name, '-v'], env=env, text=True,
                                                   stderr=subprocess.STDOUT)
                if name + ' ' + lock['version'] not in version.splitlines():
                    raise ValueError('host generator version mismatch: ' + name)
            inputs[args.sdk_profile] = profile_hash; inputs[args.sdk_build / 'manifest.json'] = manifest_hash
            report.update(sdk_binding=binding, sdk_manifest_sha256=manifest_hash, sdk_profile_sha256=profile_hash)
            run('prepare', [sys.executable, QT / 'prepare_source.py', args.archive, source])
            run('glibc-patch', ['patch', '--batch', '--fuzz=0', '-p1', '-i', PORT / 'glibc_qtcore.patch'], source)
            for path in (PORT / 'glibc_qtcore.patch', PORT / 'glibc_toolchain.cmake', QT / 'prepare_source.py'):
                inputs[path] = digest(path)
            binutils = out / 'binutils'; binutils.mkdir()
            for name in ('as', 'ld'): (binutils / name).symlink_to(tools[name]['path'])
            configure += ['-DCMAKE_TOOLCHAIN_FILE=' + str(PORT / 'glibc_toolchain.cmake'),
                '-DXOS_GLIBC_SDK=' + str(args.sdk_build / 'sysroot'), '-DXOS_GLIBC_TOOLS=' + str(binutils),
                '-DXOS_GLIBC_CXX_INCLUDES=' + ';'.join(profile['sdk_binding']['cxx_runtime']['include_directories']),
                '-DXOS_SOURCE_ROOT=' + str(ROOT), '-DQT_HOST_PATH=' + str(args.host_qt),
                '-DQT_QMAKE_TARGET_MKSPEC=xos-g++', '-DFEATURE_gui=ON', '-DFEATURE_freetype=ON',
                '-DFEATURE_harfbuzz=ON', '-DINPUT_freetype=qt', '-DINPUT_harfbuzz=qt',
                '-DINPUT_opengl=no', '-DQT_QPA_DEFAULT_PLATFORM=xos']
            configure += ['-DXOS_GLIBC_' + key + '=' + tools[name]['path'] for key, name in
                (('CC', 'gcc'), ('CXX', 'g++'), ('AR', 'ar'), ('RANLIB', 'ranlib'))]
            off = '''testlib concurrent xml widgets network sql dbus icu glib stack_protector intelcet
                stack_clash_protection poll_select poll_poll poll_ppoll poll_pollts process
                processenvironment filesystemwatcher sharedmemory systemsemaphore futimens memmem memrchr
                library dlopen system_pcre2 system_zlib opengl egl eglfs xcb xcb_xlib vulkan
                fontconfig system_freetype system_harfbuzz png jpeg gif pdf sessionmanager printsupport
                cups evdev libinput tslib linuxfb vnc directfb integrityfb vkkhrdisplay'''.split()
        configure += ['-DFEATURE_' + feature + '=OFF' for feature in off]
        run('configure', configure)
        run('build', ['cmake', '--build', build, '--parallel', args.jobs])
        run('install', ['cmake', '--install', build])
        if not args.host:
            font = source / 'src/3rdparty/wasm/DejaVuSans.ttf'
            font_target = prefix / 'share/fonts/DejaVuSans.ttf'
            font_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(font, font_target)
            inputs[font] = digest(font)
        for path, expected in inputs.items():
            if digest(path) != expected: raise ValueError('Qt input changed during build: ' + str(path))
        if not args.host and verify_profile(profile, 'glibc', args.sdk_build) != binding:
            raise ValueError('SDK changed during Qt build')
        artifacts = {path.relative_to(prefix).as_posix(): digest(path) for path in sorted(prefix.rglob('*')) if path.is_file()}
        report.update(status='qtbase_host_installed' if args.host else 'qtgui_viewport_installed', artifacts=artifacts,
                      inputs={str(path.relative_to(ROOT)): value for path, value in inputs.items()})
        save(); (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    except BaseException as error:
        report.update(status='failed', error=str(error)); save(); raise


if __name__ == '__main__': main()
