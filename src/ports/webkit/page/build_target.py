#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build and link a real software WebCore page with one complete XOS SDK."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
sys.path[:0] = [str(ROOT / 'scripts'), str(PORT.parent)]
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from target_inputs import digest, recheck_inputs, target_inputs
from xypm_sdk_profile import metadata_snapshot, verify_profile


def source_digest(root):
    result = sha256(); count = 0
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): value = 'link:' + os.readlink(path)
        elif path.is_file(): value = digest(path)
        else: continue
        result.update((path.relative_to(root).as_posix() + '\0' + value + '\n').encode()); count += 1
    return {'files': count, 'sha256': result.hexdigest()}


def bound_files(target, name, sdk_hash, expected_status, key='artifacts', prefix=None):
    record, receipt_hash = metadata_snapshot(target / name)
    if record['status'] != expected_status or record['sdk_manifest_sha256'] != sdk_hash:
        raise ValueError('dependency SDK/status mismatch: ' + str(target))
    base = target / prefix if prefix else target
    inputs = {target / name: receipt_hash}
    for relative, expected in record[key].items():
        path = base / relative
        if Path(relative).is_absolute() or '..' in Path(relative).parts or path.is_symlink():
            raise ValueError('invalid dependency artifact path: ' + relative)
        if digest(path) != expected: raise ValueError('dependency artifact mismatch: ' + relative)
        inputs[path] = expected
    return record, inputs


def build(args):
    profile, profile_hash = metadata_snapshot(args.sdk_profile)
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    if not {'cxx_runtime', 'threads', 'directories'} <= set(profile['features']):
        raise ValueError('WebCore requires a complete C++/pthread/Files SDK')
    sdk_manifest, sdk_hash = metadata_snapshot(args.sdk_build / 'manifest.json', profile['sdk_binding']['sdk_manifest_sha256'])
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib', 'strip')}
    for name, tool in tools.items():
        if not tool.get('available') or (name != 'strip' and tool['sha256'] != sdk_manifest['tools']['x86_64-elf-' + name]['sha256']):
            raise ValueError('missing or mismatched target tool: ' + name)
    prepared = json.loads((args.prepared / 'manifest.json').read_bytes())
    if (prepared['status'] != 'source_prepared' or prepared['software_lock_sha256'] != digest(PORT / 'source_lock.json')
            or prepared['recipe_sha256'] != digest(PORT / 'prepare_source.py')):
        raise ValueError('prepared source differs from the locked WebCore recipe')
    source = args.prepared / prepared['source']
    source_before = source_digest(source)
    inputs = {args.prepared / 'manifest.json': digest(args.prepared / 'manifest.json')}
    for target, status, artifact_root, headers in (
        (args.icu, 'static_icu_built', args.icu / 'install', 'include'),
        (args.fonts, 'target_font_stack_linked', None, 'prefix/include'),
        (args.xml, 'target_libxml2_linked', None, 'prefix/include'),
        (args.sqlite, 'static_sqlite_built', None, 'prefix/include'),
    ):
        _, files = target_inputs(target, status, binding['sdk_tree_sha256'], artifact_root=artifact_root, headers=headers)
        inputs.update(files)
    for target, status in ((args.fontconfig, 'target_fontconfig_linked'), (args.raster, 'target_skia_raster_linked')):
        _, files = bound_files(target, 'manifest.json', sdk_hash, status); inputs.update(files)
    backend, backend_hash = metadata_snapshot(args.font_backend / 'manifest.json')
    if (backend['status'] != 'target_skia_fontconfig_linked' or backend['c_sdk_manifest_sha256'] != sdk_hash
            or backend['raster_cxx_sdk_manifest_sha256'] != sdk_hash
            or backend['raster_target_manifest_sha256'] != digest(args.raster / 'manifest.json')
            or backend['fontconfig_target_manifest_sha256'] != digest(args.fontconfig / 'manifest.json')):
        raise ValueError('Skia font backend differs from the complete SDK/dependencies')
    inputs[args.font_backend / 'manifest.json'] = backend_hash
    inputs.update({args.font_backend / name: expected for name, expected in backend['artifacts'].items()})
    _, files = bound_files(args.webp, 'manifest.json', sdk_hash, 'static_webp_installed', 'files', 'prefix'); inputs.update(files)
    _, files = bound_files(args.openssl, 'report.json', sdk_hash, 'static_sdk_and_probe_linked', 'installed', 'prefix'); inputs.update(files)
    for directory in (args.fontconfig / 'prefix/include', args.raster / 'zlib/include',
                      args.raster / 'codecs/png/include', args.raster / 'codecs/jpeg/include'):
        headers = {path for path in directory.rglob('*') if path.is_file()}
        if not headers or not headers <= inputs.keys():
            raise ValueError('dependency compiler headers are not completely bound: ' + str(directory))
    for name in ('build_target.py', 'source_lock.json', 'prepare_source.py'):
        inputs[PORT / name] = digest(PORT / name)
    for name in ('local_page.cpp', 'local_page.html'):
        path = ROOT / 'tests/fixtures/webkit' / name; inputs[path] = digest(path)
    recheck_inputs(inputs)
    out = args.output
    if out.exists() and not args.resume: raise ValueError('output exists; select --resume for this candidate')
    if out.exists() and json.loads((out / 'build_record.json').read_bytes())['sdk_binding'] != binding:
        raise ValueError('cannot resume another SDK candidate')
    out.mkdir(parents=True, exist_ok=True)
    drivers = out / 'drivers'; (drivers / 'binutils').mkdir(parents=True, exist_ok=True)
    for name in ('cc', 'cxx'):
        if not (drivers / name).exists(): (drivers / name).symlink_to(PORT.parent / 'icu/xos-compiler')
    for name in ('as', 'ld'):
        if not (drivers / 'binutils' / name).exists(): (drivers / 'binutils' / name).symlink_to(tools[name]['path'])
    includes = drivers / 'cxx-includes.txt'
    includes.write_text('\n'.join(profile['sdk_binding']['cxx_runtime']['include_directories']) + '\n')
    native = drivers / 'include/xos'; native.mkdir(parents=True, exist_ok=True)
    native_headers = sorted((ROOT / 'src/shared/include/xos').glob('*.hpp'))
    native_headers += [ROOT / 'src/user/include/xos' / name for name in ('sdk.hpp', 'spawn.hpp')]
    for original in native_headers:
        destination = native / original.name
        if not destination.exists() or digest(destination) != digest(original): shutil.copyfile(original, destination)
        inputs[original] = digest(original); inputs[destination] = digest(destination)
    env, removed = clean_build_environment(os.environ)
    env.update(LC_ALL='C', XOS_ICU_SDK=str(args.sdk_build / 'sysroot'), XOS_ICU_CC=tools['gcc']['path'],
               XOS_ICU_CXX=tools['g++']['path'], XOS_ICU_CXX_INCLUDES=str(includes),
               COMPILER_PATH=str(drivers / 'binutils'), PKG_CONFIG_LIBDIR=str(out / 'no-host-pkgconfig'))
    report = {'status': 'building', 'sdk_binding': binding, 'sdk_profile_sha256': profile_hash,
              'sdk_manifest_sha256': sdk_hash, 'source': source_before, 'steps': [], 'target_tools': tools,
              'sanitized_environment': removed, 'guest_qualification': 'not_run'}

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
        unifdef = out / 'unifdef'
        run('host-unifdef', ['cc', '-std=gnu99', '-O2', source / 'Source/ThirdParty/unifdef/unifdef.c', '-o', unifdef])
        sdk, icu, fonts, raster = args.sdk_build / 'sysroot', args.icu / 'install', args.fonts / 'prefix', args.raster
        prefixes = [sdk, icu, fonts, args.xml / 'prefix', args.fontconfig / 'prefix', args.sqlite / 'prefix',
                    raster / 'zlib', raster / 'codecs/png', raster / 'codecs/jpeg', args.webp / 'prefix', args.openssl / 'prefix/usr']
        cmake = out / 'cmake'
        release = ('-O0 -g0 -DNDEBUG -DRELEASE_WITHOUT_OPTIMIZATIONS -Wno-sfinae-incomplete '
                   '-ffunction-sections -fdata-sections --param=ggc-min-expand=10 --param=ggc-min-heapsize=8192')
        configure = ['cmake', '-S', source, '-B', cmake, '-G', 'Ninja', '-DPORT=JSCOnly',
            '-DXOS_WEBCORE_SOFTWARE=ON', '-DENABLE_STATIC_JSC=ON', '-DUSE_SYSTEM_MALLOC=ON',
            '-DENABLE_JIT=OFF', '-DENABLE_C_LOOP=OFF', '-DENABLE_WEBASSEMBLY=OFF',
            '-DENABLE_SAMPLING_PROFILER=OFF', '-DUSE_LIBBACKTRACE=OFF', '-DUSE_SYSTEM_UNIFDEF=ON',
            '-DUNIFDEF_EXECUTABLE=' + str(unifdef), '-DUSE_THIN_ARCHIVES=ON', '-DCMAKE_DISABLE_PRECOMPILE_HEADERS=ON',
            '-DUSE_LCMS=OFF', '-DUSE_WOFF2=OFF', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_SYSTEM_NAME=XOS',
            '-DCMAKE_SYSTEM_PROCESSOR=x86_64', '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY',
            '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', '-DWEBKIT_MAX_BUNDLE_SIZE=' + str(args.bundle_size),
            '-DCMAKE_C_FLAGS_RELEASE=' + release, '-DCMAKE_CXX_FLAGS_RELEASE=' + release,
            '-DXOS_NATIVE_ABI_INCLUDE=' + str(native.parent), '-DCMAKE_SYSROOT=' + str(sdk),
            '-DCMAKE_C_COMPILER=' + str(drivers / 'cc'), '-DCMAKE_CXX_COMPILER=' + str(drivers / 'cxx'),
            '-DCMAKE_AR=' + tools['ar']['path'], '-DCMAKE_RANLIB=' + tools['ranlib']['path'],
            '-DCMAKE_FIND_ROOT_PATH=' + ';'.join(map(str, prefixes)), '-DCMAKE_PREFIX_PATH=' + ';'.join(map(str, prefixes)),
            '-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER', '-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY',
            '-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY', '-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY',
            '-DOPENSSL_ROOT_DIR=' + str(args.openssl / 'prefix/usr'),
            '-DXOS_SKIA_INCLUDE_DIRECTORY=' + str(source / 'Source/ThirdParty/skia'),
            '-DXOS_SKIA_RASTER_ARCHIVE=' + str(raster / 'cmake/libskia_raster.a'),
            '-DXOS_SKIA_FONTCONFIG_ARCHIVE=' + str(args.font_backend / 'libskia_fontconfig.a')]
        configure += ['-DENABLE_' + feature + '=OFF' for feature in
            ('WEBGL', 'WEBGPU', 'VIDEO', 'WEB_AUDIO', 'MEDIA_SOURCE', 'MEDIA_STREAM', 'WEB_RTC', 'GEOLOCATION',
             'NOTIFICATIONS', 'GAMEPAD', 'ACCESSIBILITY', 'XSLT')]
        run('configure', configure)
        run('build', ['cmake', '--build', cmake, '--target', 'WebCore', '--parallel', str(args.jobs)])
        commands = json.loads((cmake / 'compile_commands.json').read_bytes())
        command = next(item for item in commands if 'WebCore.dir/' in item['command'])
        flags = shlex.split(command['command'])
        for option in ('-o', '-c', '-MF', '-MT'):
            if option in flags:
                index = flags.index(option); del flags[index:index + 2]
        flags = [value for value in flags if value != '-MD']
        flags += ['-I', str(source / 'Source/WebCore/testing')]
        objects = []
        for name, path in (('local_page', ROOT / 'tests/fixtures/webkit/local_page.cpp'),
                           ('TestPage', source / 'Source/WebCore/testing/TestPage.cpp')):
            obj = out / (name + '.o'); objects.append(obj)
            run('compile-' + name, [*flags, '-c', path, '-o', obj], Path(command['directory']))
        archives = []
        for name in ('WebCore', 'PAL', 'JavaScriptCore', 'WTF', 'bmalloc'):
            candidates = list(cmake.rglob('lib' + name + '.a'))
            if len(candidates) != 1: raise ValueError('missing or ambiguous full archive: ' + name)
            archives += candidates
        archives += [raster / 'cmake/libskia_raster.a', args.font_backend / 'libskia_fontconfig.a',
            args.fontconfig / 'prefix/lib/libfontconfig.a', fonts / 'lib/libfreetype.a',
            fonts / 'lib/libharfbuzz.a', fonts / 'lib/libharfbuzz-icu.a',
            *(icu / ('lib/libicu' + name + '.a') for name in ('uc', 'i18n', 'data')),
            args.xml / 'prefix/lib/libxml2.a', args.sqlite / 'prefix/lib/libsqlite3.a',
            raster / 'codecs/png/lib/libpng.a', raster / 'codecs/jpeg/lib/libjpeg.a', raster / 'zlib/lib/libz.a',
            *(args.webp / ('prefix/lib/lib' + name + '.a') for name in ('webpdemux', 'webp', 'sharpyuv')),
            args.openssl / 'prefix/usr/lib/libcrypto.a']
        thin_members = {}
        for archive in archives:
            with archive.open('rb') as stream: thin = stream.read(8) == b'!<thin>\n'
            if not thin: continue
            names = subprocess.check_output([tools['ar']['path'], 't', archive], env=env, text=True).splitlines()
            if not names: raise ValueError('empty thin archive: ' + str(archive))
            for name in names:
                member = Path(name)
                if not member.is_absolute(): member = archive.parent / member
                member = member.resolve(strict=True)
                if not member.is_relative_to(cmake) or not member.is_file():
                    raise ValueError('thin archive member escapes its build: ' + name)
                thin_members[str(member.relative_to(ROOT))] = digest(member)
        inputs.update({ROOT / name: expected for name, expected in thin_members.items()})
        elf = out / 'local_page.elf'
        run('link-local-page', [drivers / 'cxx', '-Wl,--gc-sections,--no-keep-memory', *objects,
                               '-Wl,--start-group', *archives, '-Wl,--end-group', '-o', elf])
        run('strip-debug', [tools['strip']['path'], '--strip-debug', elf])
        headers = verify_elf(elf)
        recheck_inputs(inputs)
        if verify_profile(profile, 'glibc', args.sdk_build) != binding or source_digest(source) != source_before:
            raise ValueError('SDK/source changed during WebCore build')
        report.update(status='webcore_local_page_linked', elf_sha256=digest(elf), program_headers=headers,
            objects={path.name: digest(path) for path in objects},
            thin_members=thin_members,
            archives={str(path.relative_to(ROOT)): digest(path) for path in archives},
            inputs={str(path.relative_to(ROOT)): expected for path, expected in inputs.items()})
        save()
        link = {'elf_sha256': digest(elf), 'fixture_sha256': digest(ROOT / 'tests/fixtures/webkit/local_page.cpp'),
                'html_sha256': digest(ROOT / 'tests/fixtures/webkit/local_page.html'), 'sdk_manifest_sha256': sdk_hash,
                'sdk_profile_sha256': profile_hash, 'source_lock_sha256': digest(PORT.parent / 'source_lock.json'),
                'software_source_lock_sha256': digest(PORT / 'source_lock.json'),
                **{name + '_sha256': digest(PORT / (name + '.patch')) for name in ('software_context', 'software_buffers', 'software_graph')}}
        (out / 'local_page_link.json').write_text(json.dumps(link, indent=2, sort_keys=True) + '\n')
    except BaseException as error:
        report.update(status='failed', error=str(error)); save(); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-build', 'sdk-profile', 'prepared', 'icu', 'fonts', 'xml', 'fontconfig', 'raster',
                 'font-backend', 'webp', 'openssl', 'sqlite', 'output'):
        parser.add_argument('--' + name, required=True, type=lambda value: Path(value).resolve())
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--bundle-size', type=int, choices=(2, 4, 8), default=8)
    parser.add_argument('--resume', action='store_true')
    build(parser.parse_args())
