#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the prewired dual-source experiment and its scoped guest fixtures.

Build logs and the original Browser receipts are local-only. The manifest and
portable Browser receipts contain environment-variable command templates.
Choose a new output directory; existing builds and evidence are never removed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ssg_public_paths import portable


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'qt-build', 'qt-source', 'host-qt', 'binutils', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    args = p.parse_args()
    sdk, qt, qt_source, host, binutils = [getattr(args, name).resolve(strict=True)
                                          for name in ('sdk', 'qt_build', 'qt_source', 'host_qt', 'binutils')]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tools = {}
    for name in ('x86_64-elf-g++', 'x86_64-elf-gcc', 'x86_64-elf-ar'):
        found = shutil.which(name)
        if not found:
            raise SystemExit('missing tool: ' + name)
        tools[name] = Path(found)
    mappings = [('XOS_SDK_PREFIX', sdk), ('XOS_BUILD_DIR', qt), ('XOS_QT_SOURCE', qt_source),
                ('XOS_HOST_QT', host), ('XOS_BINUTILS', binutils), ('XOS_P3B_BUILD_DIR', out),
                ('XOS_PYTHON', sys.executable), ('XOS_CXX', tools['x86_64-elf-g++']),
                ('XOS_CC', tools['x86_64-elf-gcc']), ('XOS_AR', tools['x86_64-elf-ar'])]
    core = [sys.executable, ROOT / 'src/ports/qt6/build_fixture.py']
    widgets = [sys.executable, ROOT / 'src/ports/qt6/build_widgets_fixture.py']
    browser = [sys.executable, ROOT / 'src/ports/aurora_browser/build.py', '--sdk', sdk,
               '--qt-build', qt, '--qt-source', qt_source, '--host-qt', host, '--binutils', binutils]
    widgets_args = ['--sdk', sdk, '--qt-build', qt, '--qt-source', qt_source, '--core-build', qt,
                    '--host-qt', host, '--binutils', binutils, '--portable-receipt']
    core_args = ['--qrc', ROOT / 'tests/fixtures/qt6/resources.qrc', '--sdk', sdk, '--qt-build', qt,
                 '--host-qt', host, '--binutils', binutils, '--portable-receipt']
    jobs = [
        ('browser-test', browser + ['--test-structure-oracle', '--output', out / 'browser-test/browser.elf']),
        ('browser', browser + ['--output', out / 'browser/browser.elf']),
        ('notes-test', widgets + ['--source', ROOT / 'tests/fixtures/qt6/notes_live_test.cpp', *widgets_args, '--output', out / 'notes-test/notes.elf']),
        ('notes', widgets + ['--source', ROOT / 'src/ports/qt6/editor/main.cpp', *widgets_args, '--output', out / 'notes/notes.elf']),
        ('aggregate-test', core + ['--source', ROOT / 'tests/fixtures/qt6/ssg_multi_session_test.cpp', *core_args, '--output', out / 'aggregate-test/ssg-multi.elf']),
        ('aggregate', core + ['--source', ROOT / 'src/user/apps/ssg_multi_session.cpp', *core_args, '--output', out / 'aggregate/ssg-multi.elf']),
        ('consumer', core + ['--source', ROOT / 'src/user/apps/ssg_consumer.cpp', *core_args, '--output', out / 'consumer/ssg-consumer.elf']),
        ('consumer-test', core + ['--source', ROOT / 'tests/fixtures/qt6/ssg_consumer_live_test.cpp', *core_args, '--output', out / 'consumer-test/ssg-consumer.elf']),
        ('aggregate-diff-test', core + ['--source', ROOT / 'tests/fixtures/qt6/ssg_aggregate_diff_test.cpp', *core_args, '--output', out / 'aggregate-diff-test/probe.elf']),
        ('boundaries', widgets + ['--source', ROOT / 'tests/fixtures/qt6/ssg_range_boundaries.cpp', *widgets_args, '--output', out / 'boundaries/probe.elf']),
        ('session', [sys.executable, sdk / 'compile.py', ROOT / 'src/user/apps/ssg_session.cpp', '-o', out / 'session/session.elf']),
    ]
    source_patterns = ('src/user/ssg/*.hpp', 'src/user/apps/ssg_*.cpp', 'src/ports/qt6/aurora/*.*',
                       'src/ports/qt6/editor/*.*', 'src/ports/qt6/runtime/*.*',
                       'src/ports/qt6/qpa/*.*', 'src/ports/aurora_browser/*.cpp',
                       'src/ports/aurora_browser/*.hpp', 'src/ports/aurora_browser/build.py',
                       'src/ports/aurora_browser/source_lock.json', 'src/ports/aurora_browser/patches/*.patch',
                       'src/ports/qt6/build_*.py', 'tests/fixtures/qt6/ssg_*',
                       'tests/fixtures/qt6/notes_live_test.cpp', 'tests/fixtures/qt6/resources.qrc',
                       'tests/fixtures/qt6/message.txt', 'scripts/build_ssg_p3b.py')
    sources = sorted({x for pattern in source_patterns for x in ROOT.glob(pattern) if x.is_file()})
    manifest = {'status': 'BUILDING', 'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'tracked_changes': subprocess.check_output(['git', 'diff', '--name-only', 'HEAD'], cwd=ROOT, text=True).splitlines(),
                'source_sha256': {str(x.relative_to(ROOT)): sha(x) for x in sources},
                'sdk_manifest_sha256': sha(sdk / 'manifest.json'), 'qt_cache_sha256': sha(qt / 'CMakeCache.txt'),
                'tool_versions': {name: subprocess.check_output([str(tool), '--version'], text=True).splitlines()[0]
                                  for name, tool in tools.items()},
                'tool_sha256': {name: sha(tool) for name, tool in tools.items()},
                'host_qt_tool_sha256': {name: sha(host / 'libexec' / name) for name in ('moc', 'rcc')},
                'commands_kind': 'portable templates; original execution logs remain local',
                'commands': {name: portable([str(x) for x in command], mappings, strict=True) for name, command in jobs},
                'artifacts': {}}
    try:
        for name, command in jobs:
            (out / name).mkdir(parents=True, exist_ok=True)
            with (out / name / 'build.log').open('wb') as log:
                subprocess.run([str(x) for x in command], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            print('built', name, flush=True)
        for artifact in sorted(out.glob('*/*.elf')):
            manifest['artifacts'][str(artifact.relative_to(out))] = sha(artifact)
        for name in ('browser', 'browser-test'):
            original = json.loads((out / name / 'browser.receipt.json').read_text())
            sanitized = portable(original, mappings, strict=True)
            (out / name / 'browser.portable.receipt.json').write_text(json.dumps(sanitized, indent=2) + '\n')
        manifest['status'] = 'BUILT'
    except Exception as error:
        manifest['status'] = 'FAILED'
        manifest['error_type'] = type(error).__name__
        raise
    finally:
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
