#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the reusable opt-in Aurora Widgets visual library, using a matching SDK."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ('sdk','qt-build','host-qt','binutils','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();sdk,qt,host,binutils,out=[getattr(a,n).resolve() for n in ('sdk','qt_build','host_qt','binutils','output')]
here=Path(__file__).resolve().parent;out.parent.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for rel,h in json.loads((sdk/'manifest.json').read_text())['artifacts'].items():assert sha(sdk/rel)==h,rel
flags=['-std=c++17','-O2','-fPIC','-mno-red-zone','-fno-stack-protector','-ftls-model=local-exec','-D__XOS__','-DXOS_THREADED_RUNTIME','-D_POSIX_C_SOURCE=200809L','-DQT_CORE_LIB','-DQT_GUI_LIB','-DQT_WIDGETS_LIB','-DQT_NO_DEBUG','-nostdinc++','-B'+str(binutils)+'/',*['-I'+str(p) for p in (sdk/'cpp/include',sdk/'cpp/include/x86_64-elf',sdk/'include',qt/'include',qt/'include/QtCore',qt/'include/QtGui',qt/'include/QtWidgets')]]
asset=here/'aurora/assets/aurora.bmp';qrc=out.parent/'aurora.qrc';qrc.write_text('<RCC><qresource prefix="/xos"><file alias="aurora.bmp">'+str(asset)+'</file></qresource></RCC>\n')
commands=[]
def run(cmd):commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
run([host/'libexec/rcc','--name','xos_aurora',qrc,'-o',out.parent/'aurora_resource.cpp'])
objects=[]
for name,source in [('aurora_style',here/'aurora/style.cpp'),('aurora_theme',here/'aurora/theme.cpp'),('aurora_blur',here/'aurora/blur.cpp'),('aurora_semantics',here/'aurora/semantics.cpp'),('aurora_ssg',here/'aurora/ssg.cpp'),('aurora_resource',out.parent/'aurora_resource.cpp')]:
    obj=out.parent/(name+'.o');run([shutil.which('x86_64-elf-g++'),*flags,'-c',source,'-o',obj]);objects.append(obj)
run([shutil.which('x86_64-elf-ar'),'rcs',out,*objects])
inputs=[Path(__file__),asset,*sorted((here/'aurora').glob('*.hpp')),*sorted((here/'aurora').glob('*.cpp')),sdk/'manifest.json',qt/'CMakeCache.txt']
out.with_suffix('.receipt.json').write_text(json.dumps({'commands':commands,'inputs':{str(p):sha(p) for p in inputs},'library_sha256':sha(out)},indent=2)+'\n')
print('Built reusable Aurora library:',out)
