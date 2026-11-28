#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-build the software raster subset of WebKit's Skia snapshot."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import file_digest
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

port = Path(__file__).resolve().parent
root = port.parents[3]
sys.path.insert(0, str(root / 'scripts'))
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import metadata_snapshot, verify_profile


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def require_digest(path, expected):
    if digest(path) != expected:
        raise ValueError(f'{path.name} differs from the locked bytes')


def qt_sources(path, pattern):
    body, = re.findall(pattern, path.read_text(), re.MULTILINE | re.DOTALL)
    return body.split()


def build_codecs(qt, codecs, zlib, cc, ar, jobs, run):
    objects = codecs / 'objects'
    objects.mkdir(parents=True)

    def archive(library, source, groups, headers):
        prefix = codecs / library
        (prefix / 'lib').mkdir(parents=True)
        (prefix / 'include').mkdir()
        for header in headers:
            shutil.copyfile(source / header, prefix / 'include' / Path(header).name)

        def compile_member(member):
            name, suffix, flags = member
            obj = objects / (Path(name).stem + suffix + '.o')
            run(obj.stem, [cc, '-O2', *flags, '-c', source / name, '-o', obj])
            return obj

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            built = list(pool.map(compile_member, groups))
        run(library, [ar, 'rcsD', prefix / 'lib' / f'lib{library}.a', *built])
        return prefix

    png = qt / 'libpng'
    png_sources = qt_sources(png / 'CMakeLists.txt', r'^    SOURCES\n(.*?)^    DEFINES')
    png_flags = ('-DPNG_ARM_NEON_OPT=0', '-DPNG_POWERPC_VSX_OPT=0', '-DPNG_IMPEXP=', '-I' + str(zlib / 'include'))
    png_prefix = archive('png', png, [(name, '', png_flags) for name in png_sources],
                         ('png.h', 'pngconf.h', 'pnglibconf.h'))

    jpeg = qt / 'libjpeg'
    jpeg_sets = {}
    groups = []
    for bits, name in ((16, 'jpeg16_original_sources'), (12, 'jpeg12_original_sources'), (8, 'jpeg_original_sources')):
        members = []
        for token in qt_sources(jpeg / 'CMakeLists.txt', rf'^set\({name}\s+(.*?)\)'):
            members.extend(jpeg_sets[token[2:-1]] if token.startswith('${') else (token,))
        jpeg_sets[name] = members
        flags = ('-I' + str(jpeg / 'src'), f'-DBITS_IN_JSAMPLE={bits}')
        groups.extend((member, '' if bits == 8 else f'_{bits}', flags) for member in members)
    jpeg_prefix = archive('jpeg', jpeg, groups, ('src/jpeglib.h', 'src/jerror.h', 'src/jconfig.h', 'src/jmorecfg.h'))
    return png_prefix, jpeg_prefix


def write_sources(skia, output):
    contents = (skia / 'CMakeLists.txt').read_text()
    body, = re.findall(r'^add_library\(Skia STATIC\s+(.*?)^\)', contents, re.MULTILINE | re.DOTALL)
    sources = [line for raw in body.splitlines() if (line := raw.strip()) and not line.startswith('#')]
    if not all((skia / source).is_file() for source in sources):
        raise ValueError('The locked WebKit Skia target source list changed')
    raster = [source for source in sources if not source.startswith(('src/gpu/', 'src/text/gpu/'))]
    raster.extend(('src/core/SkStrikeRef.cpp', 'src/ports/SkFontHost_FreeType.cpp', 'src/ports/SkFontHost_FreeType_common.cpp',
                   'src/ports/SkOSFile_posix.cpp', 'src/ports/SkTypeface_proxy.cpp', 'src/ports/SkLog_stdio.cpp',
                   'src/ports/SkFontMgr_custom.cpp', 'src/ports/SkFontMgr_custom_empty.cpp',
                   'src/encode/SkPngEncoder_none.cpp', 'src/encode/SkJpegEncoder_none.cpp', 'src/encode/SkWebpEncoder_none.cpp'))
    raster = list(dict.fromkeys(raster))
    if not all((skia / source).is_file() for source in raster):
        raise ValueError('A CPU raster source is missing')
    output.write_text('set(skia_sources\n' + ''.join(f'    "${{XOS_SKIA_SOURCE}}/{source}"\n' for source in raster) + ')\n')
    return len(raster)


def build(args):
    source_locks = {'webkit': root / 'src/ports/webkit/source_lock.json',
                    'qtbase': root / 'src/ports/qt6/source_lock.json', 'zlib': root / 'src/ports/zlib/source_lock.json'}
    locks = {name: json.loads(path.read_bytes()) for name, path in source_locks.items()}
    archives = {'webkit': args.webkit_archive, 'qtbase': args.qtbase_archive, 'zlib': args.zlib_archive}
    for name, path in archives.items():
        require_digest(path, locks[name]['sha256'])
    profile = json.loads(args.sdk_profile.read_bytes())
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    if 'cxx_runtime' not in profile['features']:
        raise ValueError('The probe requires a complete, verified glibc C/C++ SDK')
    sdk_manifest, sdk_hash = metadata_snapshot(args.sdk_build / 'manifest.json',
                                              profile['sdk_binding']['sdk_manifest_sha256'])
    tools = {}
    for suffix in ('gcc', 'g++', 'as', 'ld', 'ar', 'ranlib'):
        name = 'x86_64-elf-' + suffix
        identity = tool_identity(name)
        if identity.get('sha256') != sdk_manifest['tools'][name]['sha256']:
            raise ValueError(f'{name} differs from the SDK build')
        tools[suffix] = identity

    font_manifest = args.font_target / 'manifest.json'
    sys.path.insert(0, str(port.parent))
    from target_inputs import recheck_inputs, target_inputs
    fonts, font_inputs = target_inputs(args.font_target, 'target_font_stack_linked', binding['sdk_tree_sha256'])
    ft = args.font_target / 'prefix'

    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    source, logs, drivers, project = (output / name for name in ('source', 'logs', 'drivers', 'project'))
    for directory in (source, logs, drivers / 'binutils', project):
        directory.mkdir(parents=True)
    fixture = project / 'raster_probe.cpp'
    fixture.write_bytes((root / 'tests/fixtures/webkit/skia_raster.cpp').read_bytes())
    stream_fixture = project / 'file_stream_probe.cpp'
    stream_fixture.write_bytes((root / 'tests/fixtures/webkit/skia_file_stream.cpp').read_bytes())
    stream_patch = project / 'file_stream.patch'
    stream_patch.write_bytes((port / 'file_stream.patch').read_bytes())
    recipe = project / 'CMakeLists.txt'
    recipe.write_bytes((port / 'CMakeLists.txt').read_bytes())
    project_inputs = {path: digest(path) for path in (fixture, stream_fixture, stream_patch, recipe)}
    for key in ('cc', 'cxx'):
        (drivers / key).symlink_to(port.parent / 'icu/xos-compiler')
    for key in ('as', 'ld'):
        (drivers / 'binutils' / key).symlink_to(tools[key]['path'])
    includes = drivers / 'includes.txt'
    includes.write_text('\n'.join(profile['sdk_binding']['cxx_runtime']['include_directories']) + '\n')
    sdk = args.sdk_build / 'sysroot'
    env, _ = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(drivers / 'binutils'), XOS_ICU_SDK=str(sdk),
               XOS_ICU_CXX_INCLUDES=str(includes), XOS_ICU_CC=tools['gcc']['path'], XOS_ICU_CXX=tools['g++']['path'])

    def run(stage, command):
        log_path = logs / (stage + '.log')
        with log_path.open('w') as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{stage} failed; see {log_path}')

    wpe_dir = locks['webkit']['archive_root']
    qt_dir = 'qtbase-everywhere-src-' + locks['qtbase']['version']
    skia_member = f'{wpe_dir}/Source/ThirdParty/skia'
    run('unpack_webkit', ['tar', '--exclude=' + skia_member + '/src/ports/fontations',
                          '-xJf', archives['webkit'], '-C', source, skia_member])
    run('unpack_qtbase', ['tar', '-xJf', archives['qtbase'], '-C', source,
                         *(f'{qt_dir}/src/3rdparty/{name}' for name in ('libjpeg', 'libpng'))])
    run('unpack_zlib', ['tar', '-xzf', archives['zlib'], '-C', source])
    roots = {'webkit': source / wpe_dir, 'qtbase': source / qt_dir}
    notices_path = port / 'notices.json'
    notice_lock = json.loads(notices_path.read_bytes())
    notices = output / 'notices'
    notices.mkdir()
    for name, value in notice_lock.items():
        member = roots[value['archive']] / value['member']
        require_digest(member, value['member_sha256'])
        normalized = b'\n'.join(line.rstrip(b' \t\r') for line in member.read_bytes().split(b'\n'))
        notice = port / 'notices' / name
        if normalized != notice.read_bytes():
            raise ValueError('Raster notice text differs from the locked upstream source')
        require_digest(notice, value['notice_sha256'])
        shutil.copyfile(notice, notices / name)

    native = ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_SYSTEM_NAME=XOS',
              '-DCMAKE_SYSTEM_PROCESSOR=x86_64', '-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY',
              f'-DCMAKE_SYSROOT={sdk}', f'-DCMAKE_C_COMPILER={drivers / "cc"}', f'-DCMAKE_CXX_COMPILER={drivers / "cxx"}',
              f'-DCMAKE_AR={tools["ar"]["path"]}', f'-DCMAKE_RANLIB={tools["ranlib"]["path"]}',
              '-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER', '-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY',
              '-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY', '-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY']
    zlib_source = source / ('zlib-' + locks['zlib']['version'])
    zlib_config = output / 'zlib-build'
    zlib = output / 'zlib'
    run('configure_zlib', ['cmake', '-S', zlib_source, '-B', zlib_config, *native, '-DZLIB_BUILD_EXAMPLES=OFF'])
    run('build_zlib', ['cmake', '--build', zlib_config, '--target', 'zlibstatic', '--parallel', str(args.jobs)])
    (zlib / 'include').mkdir(parents=True)
    (zlib / 'lib').mkdir()
    shutil.copyfile(zlib_config / 'libzlibstatic.a', zlib / 'lib/libz.a')
    shutil.copyfile(zlib_config / 'zconf.h', zlib / 'include/zconf.h')
    shutil.copyfile(zlib_source / 'zlib.h', zlib / 'include/zlib.h')
    shutil.copyfile(zlib_source / 'LICENSE', notices / 'zlib_license.txt')
    png, jpeg = build_codecs(roots['qtbase'] / 'src/3rdparty', output / 'codecs', zlib, drivers / 'cc',
                             tools['ar']['path'], args.jobs, run)

    skia = roots['webkit'] / 'Source/ThirdParty/skia'
    run('apply_file_stream_patch', ['patch', '--batch', '--fuzz=0', '-d', skia, '-p1', '-i', stream_patch])
    stream_source = skia / 'src/ports/SkOSFile_posix.cpp'
    stream_source_hash = digest(stream_source)
    sources = project / 'skia_sources.cmake'
    count = write_sources(skia, sources)
    cmake = output / 'cmake'
    prefix_paths = ';'.join(map(str, (sdk, zlib, png, jpeg, ft)))
    run('configure_skia', ['cmake', '-S', project, '-B', cmake, *native,
                           f'-DCMAKE_FIND_ROOT_PATH={prefix_paths}', f'-DXOS_SKIA_SOURCE={skia}',
                           f'-DXOS_SKIA_SOURCES={sources}', f'-DZLIB_LIBRARY={zlib / "lib/libz.a"}',
                           f'-DZLIB_INCLUDE_DIR={zlib / "include"}', f'-DPNG_LIBRARY={png / "lib/libpng.a"}',
                           f'-DPNG_PNG_INCLUDE_DIR={png / "include"}', f'-DJPEG_LIBRARY={jpeg / "lib/libjpeg.a"}',
                           f'-DJPEG_INCLUDE_DIR={jpeg / "include"}', f'-DFREETYPE_LIBRARY={ft / "lib/libfreetype.a"}',
                           f'-DFREETYPE_INCLUDE_DIR_ft2build={ft / "include/freetype2"}',
                           f'-DFREETYPE_INCLUDE_DIR_freetype2={ft / "include/freetype2"}'])
    run('build_skia', ['cmake', '--build', cmake, '--parallel', str(args.jobs)])
    probe = cmake / 'skia_raster_probe'
    stream_probe = cmake / 'skia_file_stream_probe'
    verify_elf(probe)
    verify_elf(stream_probe)
    require_digest(stream_source, stream_source_hash)
    for path, expected in project_inputs.items():
        require_digest(path, expected)
    for name, archive in archives.items():
        require_digest(archive, locks[name]['sha256'])
    recheck_inputs(font_inputs)
    if verify_profile(profile, 'glibc', args.sdk_build) != binding:
        raise ValueError('SDK changed during the raster build')
    exported = [probe, stream_probe, cmake / 'libskia_raster.a', png / 'lib/libpng.a', jpeg / 'lib/libjpeg.a',
                zlib / 'lib/libz.a', *project_inputs, sources, *(p for p in sorted(notices.iterdir()) if p.is_file())]
    exported.extend(path for prefix in (png, jpeg, zlib) for path in sorted(prefix.rglob('*')) if path.is_file())
    exported = list(dict.fromkeys(exported))
    receipt = {'status': 'target_skia_raster_linked', 'builder_sha256': digest(Path(__file__)),
               'source_locks': {k: digest(v) for k, v in source_locks.items()},
               'source_archives': {k: v['sha256'] for k, v in locks.items()},
               'sdk_manifest_sha256': sdk_hash, 'profile_binding': binding,
               'freetype_target_manifest_sha256': digest(font_manifest), 'notice_lock_sha256': digest(notices_path),
               'target_tools': {key: value['sha256'] for key, value in tools.items()}, 'skia_source_count': count,
               'skia_file_stream_source_sha256': stream_source_hash,
               'artifacts': {path.relative_to(output).as_posix(): digest(path) for path in exported}}
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('webkit-archive', 'qtbase-archive', 'zlib-archive', 'font-target', 'sdk-build', 'sdk-profile', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    build(parser.parse_args())
