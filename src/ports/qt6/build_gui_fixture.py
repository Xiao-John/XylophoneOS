#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a real static XOS QPA plugin and QtGui ELF, using frozen E15 QtCore."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
p=argparse.ArgumentParser(description=__doc__)
for n in ('source','sdk','qt-build','qt-source','core-build','host-qt','binutils','output'):
    p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args()
source,sdk,qt,qs,core,host,binutils,out=[getattr(a,n).resolve() for n in
    ('source','sdk','qt_build','qt_source','core_build','host_qt','binutils','output')]
here=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for rel,h in json.loads((sdk/'manifest.json').read_text())['artifacts'].items():
    if sha(sdk/rel)!=h: raise SystemExit('SDK mismatch: '+rel)
expected='d9435accf464ff5f7fa6d668b59c77ed5f3b5da21f2a0f56de512794aab474d3'
if sha(core/'lib/libQt6Core.a')!=expected: raise SystemExit('E15 QtCore hash mismatch')
for name in ('moc','rcc'):
    if '6.8.3' not in subprocess.check_output([host/'libexec'/name,'-v'],stderr=subprocess.STDOUT,text=True):
        raise SystemExit('Host tool version mismatch')
out.parent.mkdir(parents=True,exist_ok=True)
commands=[]
def run(cmd):
    commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
font=qs/'src/3rdparty/wasm/DejaVuSans.ttf'
qrc=out.parent/'xos_fonts.qrc'
qrc.write_text('<RCC><qresource prefix="/xos"><file alias="DejaVuSans.ttf">'+str(font)+'</file></qresource></RCC>\n')
run([host/'libexec/rcc','--name','xos_fonts',qrc,'-o',out.parent/'qrc_xos_fonts.cpp'])
flags=['-std=c++17','-O2','-fPIC','-mno-red-zone','-fno-stack-protector','-ftls-model=local-exec',
       '-D__XOS__','-DXOS_THREADED_RUNTIME','-D_POSIX_C_SOURCE=200809L','-DQT_CORE_LIB','-DQT_GUI_LIB',
       '-DQT_NO_DEBUG','-DQT_STATICPLUGIN','-nostdinc++','-B'+str(binutils)+'/',
       '-I'+str(sdk/'cpp/include'),'-I'+str(sdk/'cpp/include/x86_64-elf'),'-I'+str(sdk/'include'),
       '-I'+str(qt/'include'),'-I'+str(qt/'include/QtCore'),'-I'+str(qt/'include/QtGui'),
       '-I'+str(qt/'include/QtCore/6.8.3'),'-I'+str(qt/'include/QtCore/6.8.3/QtCore'),
       '-I'+str(qt/'include/QtGui/6.8.3'),'-I'+str(qt/'include/QtGui/6.8.3/QtGui'),
       '-I'+str(here/'runtime'),'-I'+str(out.parent)]
run([host/'libexec/moc',*[f for f in flags if f.startswith(('-I','-D'))],here/'qpa/qxos.cpp','-o',out.parent/'qxos.moc'])
cxx=shutil.which('x86_64-elf-g++');ar=shutil.which('x86_64-elf-ar')
objs=[]
for name,src in [('qxos',here/'qpa/qxos.cpp'),('fonts',out.parent/'qrc_xos_fonts.cpp'),('demo',source)]:
    obj=out.parent/(name+'.o');run([cxx,*flags,'-c',src,'-o',obj]);objs.append(obj)
plugin=out.parent/'libQXosIntegrationPlugin.a'
run([ar,'rcs',plugin,objs[0]])
archives=[qt/'lib/libQt6Gui.a',core/'lib/libQt6Core.a',core/'lib/libQt6BundledPcre2.a',
          core/'lib/libQt6BundledZLIB.a',qt/'lib/libQt6BundledFreetype.a',qt/'lib/libQt6BundledHarfbuzz.a']
# Gui's shader resource is emitted as a separate CMake object in static builds.
resources=list((qt/'src/gui').glob('CMakeFiles/Gui_resources_*.dir/.rcc/*.o'))
run([cxx,'-B'+str(binutils)+'/','-nostdlib','-static','-no-pie',
     '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
     '-T',sdk/'user.ld',sdk/'crt0_posix.o',*objs[1:],*resources,'-Wl,--start-group',plugin,*archives,
     '-Wl,--whole-archive',sdk/'lib/libxos.a','-Wl,--no-whole-archive',sdk/'cpp/lib/libstdc++.a',
     sdk/'cpp/lib/libsupc++.a',sdk/'lib/libc.a',sdk/'lib/libm.a',sdk/'cpp/lib/libgcc.a','-Wl,--end-group','-o',out])
inputs=[source,here/'qpa/qxos.cpp',here/'qpa/xos.json',Path(__file__),font,sdk/'manifest.json',*archives,*resources,plugin]
receipt={'commands':commands,'inputs':{str(p):sha(p) for p in inputs},'elf_sha256':sha(out),
         'qtcore_sha256':expected,'host_tools':{n:sha(host/'libexec'/n) for n in ('moc','rcc')}}
out.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Built real QtGui/QPA XOS ELF:',out)
