#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-build an isolated consumer of the locked WebCore HTML tokenizer."""

import argparse
from hashlib import sha256, file_digest
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

port = Path(__file__).resolve().parent
webkit = port.parent
root = webkit.parents[2]
sys.path.insert(0, str(root / 'scripts'))
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_sdk_profile import metadata_snapshot, verify_profile


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def require_digest(path, expected):
    if digest(path) != expected:
        raise ValueError(f'{path.name} differs from its locked bytes')


def verify_layout(layout, locked):
    for name, expected in locked['files'].items():
        require_digest(layout / name, expected)
    headers = {}
    for name in locked['header_roots']:
        for path in (layout / name).rglob('*'):
            if path.is_symlink():
                raise ValueError('JSC headers must be copied from the configured layout')
            if path.is_file():
                headers[path.relative_to(layout).as_posix()] = digest(path)
    checksum = sha256(json.dumps(headers, sort_keys=True).encode()).hexdigest()
    if len(headers) != locked['header_files'] or checksum != locked['header_tree_sha256']:
        raise ValueError('JSC headers differ from the companion XOS layout')


def extract_default_constructor(source, derived):
    # The other constructor depends on the generated Document settings and WebCore frame.
    options = (source / 'html/parser/HTMLParserOptions.cpp').read_text()
    span = re.search(r'(?ms)^HTMLParserOptions::HTMLParserOptions\(\).*?^}', options)
    settings = (source / 'page/SettingsBase.h').read_text()
    maximum = re.search(r'defaultMaximumHTMLParserDOMTreeDepth = (\d+);', settings)
    if not span or not maximum:
        raise ValueError('Expected the locked parser default constructor and DOM depth constant')
    implementation = span[0].replace('Settings::defaultMaximumHTMLParserDOMTreeDepth', maximum[1])
    derived.write_text('#include "config.h"\n#include "HTMLParserOptions.h"\n'
                       + 'namespace WebCore {\n' + implementation + '\n}\n')


def build(args):
    webkit_lock = webkit / 'source_lock.json'
    lock_path = port / 'inputs_lock.json'
    upstream = json.loads(webkit_lock.read_bytes())
    locked = json.loads(lock_path.read_bytes())
    icu = upstream['llint_icu']
    require_digest(args.archive, upstream['sha256'])
    require_digest(args.icu_archive, icu['archive_sha256'])
    verify_layout(args.jsc_layout, locked['jsc_layout'])
    profile = json.loads(args.sdk_profile.read_bytes())
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    if 'cxx_runtime' not in profile['features'] or binding['sdk_tree_sha256'] != icu['sdk_tree_sha256']:
        raise ValueError('The tokenizer needs the glibc C/C++ SDK used for ICU and JSC')
    sdk_manifest, sdk_digest = metadata_snapshot(args.sdk_build / 'manifest.json',
                                                profile['sdk_binding']['sdk_manifest_sha256'])
    tools = {}
    for name in ('gcc', 'g++', 'as', 'ld'):
        command = 'x86_64-elf-' + name
        item = tool_identity(command)
        if item.get('sha256') != sdk_manifest['tools'][command]['sha256']:
            raise ValueError(f'{command} differs from the bound glibc SDK toolchain')
        tools[name] = item

    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    fixture_relative = Path('tests/fixtures/webkit/html_tokenizer/probe.cpp')
    fixture_input = (root / fixture_relative).read_bytes()
    fixture_sha = sha256(fixture_input).hexdigest()
    sample_sha = digest(root / fixture_relative.with_name('page.html'))
    fixture = out / 'probe.cpp'
    fixture.write_bytes(fixture_input)
    source, icu_prefix, derived, headers, drivers, objects = (
        out / name for name in ('source', 'icu', 'derived', 'headers', 'drivers', 'objects'))
    for directory in (source, icu_prefix, derived, headers / 'JavaScriptCore', headers / 'WebCore',
                      drivers / 'binutils', objects):
        directory.mkdir(parents=True)
    env, _ = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(drivers / 'binutils'), XOS_ICU_CC=tools['gcc']['path'],
               XOS_ICU_CXX=tools['g++']['path'], XOS_ICU_SDK=str(args.sdk_build / 'sysroot'),
               XOS_ICU_CXX_INCLUDES=str(drivers / 'includes.txt'))
    (drivers / 'includes.txt').write_text('\n'.join(profile['sdk_binding']['cxx_runtime']['include_directories']) + '\n')
    driver = webkit / 'icu/xos-compiler'
    cxx = drivers / 'cxx'
    cxx.symlink_to(driver)
    for name in ('as', 'ld'):
        (drivers / 'binutils' / name).symlink_to(tools[name]['path'])

    def run(stage, command):
        log = out / (stage + '.log')
        with log.open('w') as stream:
            status = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if status.returncode:
            raise RuntimeError(f'{stage} failed; see {log}')

    archive_root = upstream['archive_root']
    members = ('Source/WebCore', 'Source/JavaScriptCore/runtime/JSExportMacros.h')
    run('unpack_webkit', ['tar', '-xJf', args.archive, '-C', source,
                          *(archive_root + '/' + name for name in members)])
    run('unpack_icu', ['tar', '--zstd', '-xf', args.icu_archive, '-C', icu_prefix])
    for name, checksum in icu['artifacts'].items():
        require_digest(icu_prefix / name, checksum)
    source /= archive_root
    for name, notice in locked['notices'].items():
        member = source / notice['member']
        require_digest(member, notice['sha256'])
        normalized = b'\n'.join(line.rstrip(b' \t') for line in member.read_bytes().split(b'\n'))
        if normalized != (port / name).read_bytes():
            raise ValueError('WebCore notice differs from the locked upstream text')
        require_digest(port / name, notice['notice_sha256'])
    webcore = source / 'Source/WebCore'
    html = webcore / 'html/parser'
    forwarding = {'JavaScriptCore/JSExportMacros.h': source / members[-1],
                  'WebCore/PlatformExportMacros.h': webcore / 'PlatformExportMacros.h',
                  'WebCore/CommonAtomStrings.h': webcore / 'platform/CommonAtomStrings.h',
                  'WebCore/QualifiedName.h': webcore / 'dom/QualifiedName.h'}
    for name, target in forwarding.items():
        (headers / name).symlink_to(target)
    run('html_entity_table', [sys.executable, html / 'create-html-entity-table', '-o',
                              derived / 'HTMLEntityTable.cpp', html / 'HTMLEntityNames.in'])
    run('html_names', ['perl', webcore / 'dom/make_names.pl', '--outputDir', derived, '--attrs',
                       webcore / 'html/HTMLAttributeNames.in', '--elements', webcore / 'html/HTMLTagNames.in'])
    defaults = derived / 'html_parser_defaults.cpp'
    extract_default_constructor(webcore, defaults)
    sources = [html / name for name in ('HTMLTokenizer.cpp', 'HTMLEntityParser.cpp', 'HTMLEntitySearch.cpp')]
    sources.extend((webcore / 'platform/text/SegmentedString.cpp', derived / 'HTMLEntityTable.cpp', defaults, fixture))
    includes = [derived, headers, webcore, webcore / 'html', html, webcore / 'dom', webcore / 'css/parser',
                webcore / 'platform', webcore / 'platform/text', webcore / 'PAL', args.jsc_layout,
                *(args.jsc_layout / name for name in locked['jsc_layout']['header_roots']), icu_prefix / 'include']
    flags = ['-std=c++23', '-O1', '-ffunction-sections', '-fdata-sections', '-DNDEBUG',
             '-DBUILDING_WITH_CMAKE=1', '-DHAVE_CONFIG_H=1', f'-ffile-prefix-map={out}=.']
    for directory in includes:
        flags.extend(('-I', directory))
    compiled = []
    for name in sources:
        obj = objects / (name.stem + '.o')
        run(name.stem, [cxx, *flags, '-c', name, '-o', obj])
        compiled.append(obj)
    selected = out / 'html_slice.o'
    # Select only the fixture's reachable WebCore code before CRT and SDK archives enter the link.
    run('partial_link', [tools['ld']['path'], '-r', '--gc-sections', '-u', 'main', *compiled, '-o', selected])
    executable = out / 'html_slice.elf'
    run('link', [cxx, selected, '-Wl,--start-group', args.jsc_layout / 'lib/libWTF.a',
                 args.jsc_layout / 'lib/libbmalloc.a', *(icu_prefix / name for name in icu['artifacts']),
                 '-Wl,--end-group', '-o', executable])
    verify_elf(executable)
    require_digest(fixture, fixture_sha)
    require_digest(args.archive, upstream['sha256'])
    require_digest(args.icu_archive, icu['archive_sha256'])
    verify_layout(args.jsc_layout, locked['jsc_layout'])
    if verify_profile(profile, 'glibc', args.sdk_build) != binding:
        raise ValueError('SDK inputs changed during the tokenizer build')
    input_sources = {p.relative_to(out).as_posix(): digest(p) for p in sources if p != fixture}
    input_sources[fixture_relative.as_posix()] = fixture_sha
    receipt = {'status': 'target_webcore_html_tokenizer_linked', 'builder_sha256': digest(Path(__file__)),
               'input_lock_sha256': digest(lock_path), 'source_lock_sha256': digest(webkit_lock),
               'webkit_archive_sha256': upstream['sha256'], 'icu_archive_sha256': icu['archive_sha256'],
               'sdk_manifest_sha256': sdk_digest, 'profile_binding': binding, 'driver_sha256': digest(driver),
               'fixture_sha256': fixture_sha, 'sample_sha256': sample_sha,
               'target_tools': {name: item['sha256'] for name, item in tools.items()},
               'input_sources': input_sources,
               'artifacts': {p.relative_to(out).as_posix(): digest(p) for p in (*compiled, selected, executable, fixture)}}
    (out / 'manifest.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'icu-archive', 'sdk-build', 'sdk-profile', 'jsc-layout', 'output'):
        parser.add_argument('--' + name, type=lambda value: Path(value).resolve(), required=True)
    build(parser.parse_args())
