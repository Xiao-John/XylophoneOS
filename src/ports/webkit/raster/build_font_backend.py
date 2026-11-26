#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build upstream Skia's Fontconfig backend against the XOS target archives."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from build_target import clean_build_environment, digest, require_digest, root, tool_identity, verify_elf


def manifest(path):
    receipt = path / 'manifest.json'
    data = receipt.read_bytes()
    return json.loads(data), sha256(data).hexdigest()


def build(args):
    raster, raster_hash = manifest(args.raster)
    config, config_hash = manifest(args.fontconfig)
    fonts, fonts_hash = manifest(args.fonts)
    xml, xml_hash = manifest(args.xml)
    cxx, cxx_hash = manifest(args.cxx_sdk)
    c, c_hash = manifest(args.c_sdk)
    if (raster['status'] != 'target_skia_raster_linked'
        or config['status'] != 'target_fontconfig_linked'
        or fonts['status'] != 'target_font_stack_linked'
        or xml['status'] != 'target_libxml2_linked'
        or c['status'] != 'static_sdk_built'
        or cxx['status'] != 'static_sdk_built'
        or cxx['cxx_runtime']['status'] != 'built'
        or c['source_sha256'] != cxx['source_sha256']
        or raster['sdk_manifest_sha256'] != cxx_hash
        or raster['freetype_target_manifest_sha256'] != fonts_hash
        or config['sdk_manifest_sha256'] != c_hash
        or config['font_target_manifest_sha256'] != fonts_hash
        or config['xml_target_manifest_sha256'] != xml_hash):
        raise ValueError('Skia and Fontconfig dependencies do not match their bound builds')

    cpp_root = args.cxx_sdk / 'sysroot'
    c_root = args.c_sdk / 'sysroot'
    fixture = root / 'tests/fixtures/webkit/skia_fontconfig.cpp'
    webkit_lock = root / 'src/ports/webkit/source_lock.json'
    stream_patch = Path(__file__).with_name('fontconfig_file_stream.patch')
    locked = json.loads(webkit_lock.read_bytes())
    if raster['source_archives']['webkit'] != locked['sha256']:
        raise ValueError('Raster Skia comes from a different WebKit release')
    base_inputs = {args.webkit_archive: locked['sha256'], fixture: digest(fixture),
                   webkit_lock: digest(webkit_lock), stream_patch: digest(stream_patch)}
    builds = ((args.raster, raster_hash), (args.fontconfig, config_hash),
              (args.fonts, fonts_hash), (args.xml, xml_hash),
              (args.cxx_sdk, cxx_hash), (args.c_sdk, c_hash))
    for location, expected in builds:
        base_inputs[location / 'manifest.json'] = expected

    def artifacts(location, receipt, names):
        result = [location / name for name in names]
        base_inputs.update({location / name: receipt['artifacts'][name] for name in names})
        return result

    libraries = artifacts(args.raster, raster, ('cmake/libskia_raster.a', 'codecs/png/lib/libpng.a',
                                                 'codecs/jpeg/lib/libjpeg.a', 'zlib/lib/libz.a'))
    libraries += artifacts(args.fontconfig, config, ('prefix/lib/libfontconfig.a',))
    libraries += artifacts(args.fonts, fonts, ('prefix/lib/libfreetype.a',))
    libraries += artifacts(args.xml, xml, ('prefix/lib/libxml2.a',))
    crt = artifacts(c_root, c, ('usr/lib/xos_start.o', 'usr/lib/crti.o', 'usr/lib/crtbegin.o',
                                'usr/lib/xos_start_c.o', 'usr/lib/crtend.o', 'usr/lib/crtn.o', 'user.ld'))
    libraries += artifacts(c_root, c, ('usr/lib/libc.a',))
    if base_inputs[libraries[-1]] != config['sdk_libc_sha256']:
        raise ValueError('Fontconfig libc differs from the supplied replacement')
    libraries += artifacts(c_root, c, ('usr/lib/libm.a', 'usr/lib/libxos_terminal.a'))
    libraries += artifacts(cpp_root, cxx, ('usr/lib/libstdc++.a', 'usr/lib/libsupc++.a', 'usr/lib/libgcc.a'))
    for name, expected in cxx['artifacts'].items():
        if name.startswith('usr/include/c++/'):
            base_inputs[cpp_root / name] = expected
    for name, expected in c['artifacts'].items():
        if name.startswith(('usr/include/', 'usr/lib/compiler-include/')):
            base_inputs[c_root / name] = expected
    for name, expected in config['artifacts'].items():
        if name.startswith('prefix/include/fontconfig/'):
            base_inputs[args.fontconfig / name] = expected
    for path, expected in base_inputs.items():
        require_digest(path, expected)

    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('g++', 'as', 'ld', 'ar')}
    for name, data in tools.items():
        tool = 'x86_64-elf-' + name
        if not data['available'] or data['sha256'] != cxx['tools'][tool]['sha256'] or data['sha256'] != c['tools'][tool]['sha256']:
            raise ValueError(f'{tool} differs from the bound SDKs')
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'source'
    source.mkdir()
    binutils = output / 'binutils'
    binutils.mkdir()
    for name in ('as', 'ld'):
        (binutils / name).symlink_to(tools[name]['path'])
    env, _ = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(binutils))

    def run(stage, command):
        log = output / (stage + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{stage} failed; see {log}')

    skia_member = locked['archive_root'] + '/Source/ThirdParty/skia'
    run('unpack', ['tar', '--exclude=' + skia_member + '/src/ports/fontations', '-xJf', args.webkit_archive,
                   '-C', source, skia_member])
    skia = source / skia_member
    backend = skia / 'src/ports/SkFontMgr_fontconfig.cpp'
    original_backend_hash = digest(backend)
    run('patch', ['patch', '--batch', '--fuzz=0', '-d', skia, '-p1', '-i', stream_patch])
    base_inputs[backend] = digest(backend)
    include = [cpp_root / directory for directory in cxx['cxx_runtime']['include_directories']]
    include.extend((c_root / 'usr/include', c_root / 'usr/lib/compiler-include'))
    driver = [tools['g++']['path'], '--sysroot=' + str(c_root), '-mno-red-zone', '-fno-pie', '-fno-pic',
              '-ftls-model=local-exec', '-D__XOS__', '-D_GNU_SOURCE=1', '-nostdinc', '-nostdinc++']
    for directory in include:
        driver.extend(('-isystem', directory))
    flags = ['-std=c++20', '-O1', '-fdata-sections', '-ffunction-sections', '-I', skia,
             '-I', args.fontconfig / 'prefix/include', '-DSK_BUILD_FOR_UNIX', '-DSKIA_IMPLEMENTATION=1',
             '-DSK_RELEASE', '-DSK_ASSUME_GL=0', '-DSK_ASSUME_GL_ES=0', '-DSK_ASSUME_WEBGL=0',
             '-DSK_USER_CONFIG_HEADER="./WebKitSkiaConfig.h"']
    backend_object = output / 'SkFontMgr_fontconfig.o'
    archive = output / 'libskia_fontconfig.a'
    executable = output / 'skia_fontconfig.elf'
    run('compile_backend', [*driver, *flags, '-c', backend, '-o', backend_object])
    run('archive', [tools['ar']['path'], 'rcsD', archive, backend_object])
    run('link', [*driver, *flags, '-static', '-no-pie', '-nostdlib', '-T', crt[-1],
                 '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
                 *crt[:4], fixture, '-Wl,--start-group', archive, *libraries, '-Wl,--end-group',
                 *crt[4:6], '-o', executable])
    verify_elf(executable)
    for path, expected in base_inputs.items():
        require_digest(path, expected)
    report = {'status': 'target_skia_fontconfig_linked', 'raster_target_manifest_sha256': raster_hash,
              'fontconfig_target_manifest_sha256': config_hash, 'font_target_manifest_sha256': fonts_hash,
              'xml_target_manifest_sha256': xml_hash, 'raster_cxx_sdk_manifest_sha256': cxx_hash,
              'c_sdk_manifest_sha256': c_hash, 'libc_sha256': config['sdk_libc_sha256'],
              'original_font_manager_sha256': original_backend_hash, 'font_manager_source_sha256': base_inputs[backend],
              'stream_patch_sha256': base_inputs[stream_patch], 'fixture_sha256': base_inputs[fixture],
              'build_recipe_sha256': digest(Path(__file__)),
              'tools': {name: data['sha256'] for name, data in tools.items()},
              'artifacts': {artifact.name: digest(artifact) for artifact in (archive, backend_object, executable)}}
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('webkit-archive', 'raster', 'fontconfig', 'fonts', 'xml', 'cxx-sdk', 'c-sdk', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    build(parser.parse_args())
