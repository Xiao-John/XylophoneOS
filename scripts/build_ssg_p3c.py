#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the watch supervisor and contract probe into a fresh directory."""
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
    for name in ('sdk', 'qt-build', 'host-qt', 'binutils', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    sdk, qt, host, binutils = [getattr(a, name).resolve(strict=True) for name in ('sdk', 'qt_build', 'host_qt', 'binutils')]
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which('x86_64-elf-g++')
    if not compiler:
        raise SystemExit('missing x86_64-elf-g++')
    mappings = [('XOS_SDK_PREFIX', sdk), ('XOS_BUILD_DIR', qt), ('XOS_HOST_QT', host),
                ('XOS_BINUTILS', binutils), ('XOS_P3C_BUILD_DIR', out),
                ('XOS_PYTHON', sys.executable), ('XOS_CXX', compiler)]
    common = [sys.executable, ROOT / 'src/ports/qt6/build_fixture.py', '--qrc', ROOT / 'tests/fixtures/qt6/resources.qrc',
              '--sdk', sdk, '--qt-build', qt, '--host-qt', host, '--binutils', binutils, '--portable-receipt']
    jobs = [('supervisor', ROOT / 'src/user/apps/ssg_multi_session.cpp'),
            ('supervisor-test', ROOT / 'tests/fixtures/qt6/ssg_multi_session_test.cpp'),
            ('contract-test', ROOT / 'tests/fixtures/qt6/ssg_watch_contract_test.cpp')]
    sources = sorted({p for pattern in ('src/user/ssg/*.hpp', 'src/user/apps/ssg_multi_session.cpp',
                                        'tests/fixtures/qt6/ssg_multi_session_test.cpp',
                                        'tests/fixtures/qt6/ssg_watch_contract_test.cpp',
                                        'tests/fixtures/qt6/resources.qrc', 'tests/fixtures/qt6/message.txt',
                                        'src/ports/qt6/build_fixture.py', 'scripts/build_ssg_p3c.py')
                      for p in ROOT.glob(pattern) if p.is_file()})
    manifest = {'status': 'BUILDING', 'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'source_sha256': {str(path.relative_to(ROOT)): sha(path) for path in sources},
                'sdk_manifest_sha256': sha(sdk / 'manifest.json'), 'qt_cache_sha256': sha(qt / 'CMakeCache.txt'),
                'compiler_version': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
                'compiler_sha256': sha(compiler), 'host_rcc_sha256': sha(host / 'libexec/rcc'),
                'commands': {}, 'artifacts': {}}
    try:
        for name, source in jobs:
            target = out / name / (name + '.elf')
            target.parent.mkdir()
            cmd = common + ['--source', source, '--output', target]
            manifest['commands'][name] = portable([str(part) for part in cmd], mappings, strict=True)
            with (target.parent / 'build.log').open('wb') as log:
                subprocess.run([str(part) for part in cmd], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
            manifest['artifacts'][str(target.relative_to(out))] = sha(target)
            print('built', name, flush=True)
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
