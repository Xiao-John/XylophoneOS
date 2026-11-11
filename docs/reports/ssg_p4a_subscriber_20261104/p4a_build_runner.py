#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Cross-build P4A providers, supervisor, independent Subscriber, and checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from ssg_public_paths import portable


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'qt-build', 'qt-source', 'host-qt', 'binutils', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    sdk, qt, qt_source, host, binutils = [getattr(args, name.replace('-', '_')).resolve(strict=True)
                                          for name in ('sdk', 'qt-build', 'qt-source', 'host-qt', 'binutils')]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which('x86_64-elf-g++')
    c_compiler = shutil.which('x86_64-elf-gcc')
    archiver = shutil.which('x86_64-elf-ar')
    if not compiler or not c_compiler or not archiver:
        raise SystemExit('missing XOS target compiler or archiver')
    mappings = [('XOS_SDK_PREFIX', sdk), ('XOS_BUILD_DIR', qt), ('XOS_QT_SOURCE', qt_source),
                ('XOS_HOST_QT', host),
                ('XOS_BINUTILS', binutils), ('XOS_P4A_BUILD_DIR', output),
                ('XOS_PYTHON', sys.executable), ('XOS_CXX', compiler),
                ('XOS_CC', c_compiler), ('XOS_AR', archiver)]
    core_builder = [sys.executable, root / 'src/ports/qt6/build_fixture.py',
              '--qrc', root / 'tests/fixtures/qt6/resources.qrc', '--sdk', sdk,
              '--qt-build', qt, '--host-qt', host, '--binutils', binutils, '--portable-receipt']
    widgets_builder = [sys.executable, root / 'src/ports/qt6/build_widgets_fixture.py']
    widgets_args = ['--sdk', sdk, '--qt-build', qt, '--qt-source', qt_source, '--core-build', qt,
                    '--host-qt', host, '--binutils', binutils, '--portable-receipt']
    browser_builder = [sys.executable, root / 'src/ports/aurora_browser/build.py', '--sdk', sdk,
                       '--qt-build', qt, '--qt-source', qt_source, '--host-qt', host, '--binutils', binutils]
    jobs = [
        ('browser', browser_builder + ['--output', output / 'browser/browser.elf']),
        ('browser-test', browser_builder + ['--test-structure-oracle', '--output', output / 'browser-test/browser.elf']),
        ('notes', widgets_builder + ['--source', root / 'src/ports/qt6/editor/main.cpp', *widgets_args,
                                    '--output', output / 'notes/notes.elf']),
        ('notes-test', widgets_builder + ['--source', root / 'tests/fixtures/qt6/notes_live_test.cpp', *widgets_args,
                                          '--output', output / 'notes-test/notes.elf']),
        ('supervisor', core_builder + ['--source', root / 'src/user/apps/ssg_multi_session.cpp',
                                       '--output', output / 'supervisor/supervisor.elf']),
        ('supervisor-test', core_builder + ['--source', root / 'tests/fixtures/qt6/ssg_multi_session_test.cpp',
                                            '--output', output / 'supervisor-test/supervisor-test.elf']),
        ('subscriber', core_builder + ['--source', root / 'src/user/apps/ssg_subscriber.cpp',
                                       '--output', output / 'subscriber/subscriber.elf']),
        ('contract-test', core_builder + ['--source', root / 'tests/fixtures/qt6/ssg_watch_contract_test.cpp',
                                          '--output', output / 'contract-test/contract-test.elf']),
        ('subscriber-state-test', core_builder + ['--source', root / 'tests/fixtures/qt6/ssg_p4a_state_test.cpp',
                                                  '--output', output / 'subscriber-state-test/subscriber-state-test.elf']),
    ]
    patterns = ('src/user/ssg/*.hpp', 'src/user/apps/ssg_multi_session.cpp',
                'src/user/apps/ssg_subscriber.cpp', 'tests/fixtures/qt6/ssg_multi_session_test.cpp',
                'tests/fixtures/qt6/ssg_watch_contract_test.cpp', 'tests/fixtures/qt6/ssg_p4a_state_test.cpp',
                'tests/fixtures/qt6/resources.qrc',
                'tests/fixtures/qt6/message.txt', 'tests/fixtures/qt6/notes_live_test.cpp',
                'src/ports/qt6/build_fixture.py', 'src/ports/qt6/build_widgets_fixture.py',
                'src/ports/qt6/editor/*.cpp', 'src/ports/qt6/editor/*.hpp',
                'src/ports/qt6/qpa/*.cpp', 'src/ports/qt6/qpa/*.json',
                'src/ports/qt6/runtime/*.*', 'src/ports/qt6/aurora/*.cpp',
                'src/ports/qt6/aurora/*.hpp', 'src/ports/qt6/aurora/*.md',
                'src/ports/qt6/build_aurora.py', 'src/ports/aurora_browser/*.cpp',
                'src/ports/aurora_browser/*.hpp', 'src/ports/aurora_browser/build.py',
                'src/ports/aurora_browser/source_lock.json',
                'src/ports/aurora_browser/patches/*.patch', 'scripts/build_ssg_p4a.py',
                'scripts/prepare_ssg_p4a_toolchain.py')
    sources = sorted({path for pattern in patterns for path in root.glob(pattern) if path.is_file()})
    manifest = {
        'status': 'BUILDING',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'source_sha256': {str(path.relative_to(root)): sha(path) for path in sources},
        'sdk_manifest_sha256': sha(sdk / 'manifest.json'),
        'qt_cache_sha256': sha(qt / 'CMakeCache.txt'),
        'compiler_version': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
        'compiler_sha256': sha(compiler),
        'host_moc_sha256': sha(host / 'libexec/moc'),
        'host_rcc_sha256': sha(host / 'libexec/rcc'),
        'commands': {},
        'artifacts': {},
    }
    try:
        for name, command in jobs:
            target = Path(command[-1])
            target.parent.mkdir(parents=True)
            manifest['commands'][name] = portable([str(value) for value in command], mappings, strict=True)
            with (target.parent / 'build.log').open('wb') as log:
                subprocess.run([str(value) for value in command], cwd=root,
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            manifest['artifacts'][str(target.relative_to(output))] = sha(target)
            print('built', name, flush=True)
        for name in ('browser', 'browser-test'):
            original = json.loads((output / name / 'browser.receipt.json').read_text())
            sanitized = portable(original, mappings, strict=True)
            portable_receipt = output / name / 'browser.portable.receipt.json'
            portable_receipt.write_text(json.dumps(sanitized, indent=2) + '\n')
            manifest['artifacts'][str(portable_receipt.relative_to(output))] = sha(portable_receipt)
        manifest['status'] = 'BUILT'
    except Exception as error:
        manifest['status'] = 'FAILED'
        manifest['error_type'] = type(error).__name__
        raise
    finally:
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
