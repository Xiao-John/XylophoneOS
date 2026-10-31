#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the restricted prewired SSG experiment from a matched XOS Qt SDK."""
import argparse, hashlib, json, shutil, subprocess, sys
from pathlib import Path

from ssg_public_paths import portable
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
for name in ('sdk','qt-build','qt-source','host-qt','binutils','output'):
    p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
sdk,qt,source,host,binutils,out=(getattr(a,n).resolve() for n in ('sdk','qt_build','qt_source','host_qt','binutils','output'))
out.mkdir(parents=True,exist_ok=False)
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
commands=[
    [sys.executable,sdk/'compile.py',ROOT/'src/user/apps/ssg_session.cpp','-o',out/'session.elf'],
    [sys.executable,ROOT/'src/ports/qt6/build_fixture.py','--source',ROOT/'src/user/apps/ssg_consumer.cpp',
     '--qrc',ROOT/'tests/fixtures/qt6/resources.qrc','--sdk',sdk,'--qt-build',qt,'--host-qt',host,
     '--binutils',binutils,'--portable-receipt','--output',out/'consumer/ssg-consumer.elf'],
    [sys.executable,ROOT/'src/ports/qt6/build_widgets_fixture.py','--source',ROOT/'src/ports/qt6/editor/main.cpp',
     '--sdk',sdk,'--qt-build',qt,'--qt-source',source,'--core-build',qt,'--host-qt',host,
     '--binutils',binutils,'--portable-receipt','--output',out/'notes/notes.elf'],
    [sys.executable,ROOT/'src/ports/aurora_browser/build.py','--sdk',sdk,'--qt-build',qt,
     '--qt-source',source,'--host-qt',host,'--binutils',binutils,'--output',out/'browser/browser.elf'],
]
inputs=[
    'scripts/build_ssg_p1.py','src/user/apps/ssg_session.cpp','src/user/apps/ssg_consumer.cpp',
    'src/user/ssg/pipe_wire.hpp','src/ports/qt6/aurora/ssg_pipe_provider.hpp',
    'src/ports/qt6/aurora/ssg.cpp','src/ports/qt6/aurora/ssg.hpp','src/ports/qt6/editor/main.cpp',
    'src/ports/aurora_browser/main.cpp','src/ports/aurora_browser/view.hpp',
    'src/ports/aurora_browser/scene_geometry.hpp','src/ports/aurora_browser/content.hpp',
    'src/ports/aurora_browser/patches/0001_readonly_render_fragments.patch',
    'src/ports/aurora_browser/source_lock.json','tests/ssg_ipc_guest.py',
]
manifest={'status':'BUILDING','commands_kind':'templates; execution uses the original runtime arguments', 'commands':[[str(x) for x in c] for c in commands],
          'source_sha256':{str(x):sha(ROOT/x) for x in inputs},
          'sdk_manifest_sha256':sha(sdk/'manifest.json'),'qt_cache_sha256':sha(qt/'CMakeCache.txt'),
          'output':str(out),'tools':{}}
try:
    for tool in ('x86_64-elf-g++','x86_64-elf-gcc','x86_64-elf-ar'):
        path=Path(shutil.which(tool) or '').resolve(strict=True)
        manifest['tools'][tool]={'path':str(path),'sha256':sha(path),
            'version':subprocess.check_output([str(path),'--version'],text=True).splitlines()[0]}
    for i,cmd in enumerate(commands):
        with (out/f'build-{i+1}.log').open('wb') as log:
            subprocess.run([str(x) for x in cmd],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        print('built',i+1,'of',len(commands),flush=True)
    manifest['artifacts']={str(x.relative_to(out)):sha(x) for x in (
        out/'session.elf',out/'consumer/ssg-consumer.elf',out/'notes/notes.elf',out/'browser/browser.elf')}
    manifest['status']='BUILT'
except Exception as e:
    manifest['error']=repr(e)
    raise
finally:
    mappings=[('XOS_SDK_PREFIX',sdk),('XOS_BUILD_DIR',qt),('XOS_QT_SOURCE',source),('XOS_HOST_QT',host),('XOS_BINUTILS',binutils),('XOS_TEST_OUT',out),('XOS_PYTHON',sys.executable),('XOS_CXX',shutil.which('x86_64-elf-g++')),('XOS_CC',shutil.which('x86_64-elf-gcc')),('XOS_AR',shutil.which('x86_64-elf-ar'))]
    (out/'manifest.json').write_text(json.dumps(portable(manifest,mappings,strict=True),indent=2)+'\n')
