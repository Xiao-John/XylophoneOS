#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the reusable opt-in Aurora Widgets visual library, using a matching SDK."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for n in ('sdk','qt-build','host-qt','binutils','output'):p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--include-overlay',type=Path)
a=p.parse_args();sdk,qt,host,binutils,out=[getattr(a,n).resolve() for n in ('sdk','qt_build','host_qt','binutils','output')]
overlay=a.include_overlay.resolve() if a.include_overlay else qt/'include'
here=Path(__file__).resolve().parent;out.parent.mkdir(parents=True,exist_ok=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def host_tool(name):
    path=host/'libexec'/name
    if not path.is_file() and Path(str(path)+'.exe').is_file():
        path=Path(str(path)+'.exe')
    return path
for tool in ('x86_64-elf-g++','x86_64-elf-ar'):
    if not shutil.which(tool):raise SystemExit('missing '+tool+' in PATH')
sdk_metadata=json.loads((sdk/'manifest.json').read_text());sdk_release=sdk/'release.json'
release_drift=set()
if 'artifacts' in sdk_metadata:sdk_files=sdk_metadata['artifacts']
else:
    release=json.loads(sdk_release.read_text())
    if release.get('version')!='0.0.2-1103' or release.get('system_build_id')!=sdk_metadata.get('build_id'):
        raise SystemExit('SDK release/system identity mismatch')
    sdk_files=release.get('sdk_binding',{}).get('packaged',{}).get('files',{})
    if not sdk_files:raise SystemExit('SDK has no published file binding')
    release_drift={'DEVELOPING.md','docs/releases/SDK_DEVELOPING.md','licenses/open_items.json','tools/xos_app.py'}
    missing=release_drift-set(sdk_files)
    if missing:raise SystemExit('SDK drift allowlist does not match release binding: '+', '.join(sorted(missing)))
    required={'crt0_posix.o','user.ld','lib/libxos.a','lib/libc.a','lib/libm.a','cpp/lib/libstdc++.a','cpp/lib/libsupc++.a','cpp/lib/libgcc.a'}
    if required-set(sdk_files):raise SystemExit('SDK binding omits required runtime files')
    for rel in sorted(release_drift):print('Known release SDK binding drift (not used for Qt link): '+rel)
for rel,h in sdk_files.items():
    if rel in release_drift:continue
    if sha(sdk/rel)!=h:raise SystemExit('SDK mismatch: '+rel)
flags=['-std=c++17','-O2','-fPIC','-mno-red-zone','-fno-stack-protector','-ftls-model=local-exec','-D__XOS__','-DXOS_THREADED_RUNTIME','-D_POSIX_C_SOURCE=200809L','-DQT_CORE_LIB','-DQT_GUI_LIB','-DQT_WIDGETS_LIB','-DQT_NO_DEBUG','-nostdinc++','-B'+str(binutils)+'/',*['-I'+str(p) for p in (here/'aurora',sdk/'cpp/include',sdk/'cpp/include/x86_64-elf',sdk/'cpp/include/c++/16.2.0',sdk/'cpp/include/c++/16.2.0/x86_64-unknown-elf',sdk/'include',overlay,qt/'include',qt/'include/QtCore',qt/'include/QtGui',qt/'include/QtWidgets')]]
asset=here/'aurora/assets/aurora.bmp';qrc=out.parent/'aurora.qrc';qrc.write_text('<RCC><qresource prefix="/xos"><file alias="aurora.bmp">'+str(asset)+'</file></qresource></RCC>\n')
cache=qt/'CMakeCache.txt';asset_manifest=qt.parent/'asset_manifest.json'
if cache.is_file():qt_inputs=[cache]
elif asset_manifest.is_file():
    assets=json.loads(asset_manifest.read_text())
    if assets.get('qt_version')!='6.8.3' or assets.get('files',{}).get(qt.name+'/lib/libQt6Core.a')!=sha(qt/'lib/libQt6Core.a'):
        raise SystemExit('Qt release asset mismatch')
    core_key=qt.name+'/lib/libQt6Core.a'
    if assets.get('files',{}).get(core_key)!=sha(qt/'lib/libQt6Core.a'):
        raise SystemExit('Qt release asset mismatch: '+core_key)
    qt_inputs=[asset_manifest]
else:raise SystemExit('Qt build cache or release asset manifest required')
commands=[]
def run(cmd):commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
run([host_tool('rcc'),'--name','xos_aurora',qrc,'-o',out.parent/'aurora_resource.cpp'])
objects=[]
for name,source in [('aurora_style',here/'aurora/style.cpp'),('aurora_theme',here/'aurora/theme.cpp'),('aurora_blur',here/'aurora/blur.cpp'),('aurora_semantics',here/'aurora/semantics.cpp'),('aurora_ssg',here/'aurora/ssg.cpp'),('aurora_resource',out.parent/'aurora_resource.cpp')]:
    obj=out.parent/(name+'.o');run([shutil.which('x86_64-elf-g++'),*flags,'-c',source,'-o',obj]);objects.append(obj)
out.unlink(missing_ok=True)
run([shutil.which('x86_64-elf-ar'),'rcs',out.as_posix(),*[p.as_posix() for p in objects]])
inputs=[Path(__file__),asset,*sorted((here/'aurora').glob('*.hpp')),*sorted((here/'aurora').glob('*.cpp')),sdk/'manifest.json',*([sdk_release] if sdk_release.is_file() else []),*qt_inputs,*[f for f in overlay.rglob('*') if f.is_file()]]
out.with_suffix('.receipt.json').write_text(json.dumps({'commands':commands,'inputs':{str(p):sha(p) for p in inputs},'library_sha256':sha(out)},indent=2)+'\n')
print('Built reusable Aurora library:',out)
