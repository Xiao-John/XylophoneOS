#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a real XOS Qt Widgets ELF from one matching Qt/SDK build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from ssg_public_paths import portable
p=argparse.ArgumentParser(description=__doc__)
for n in ('source','sdk','qt-build','qt-source','core-build','host-qt','binutils','output'):
    p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--wrap', action='append', default=[])
p.add_argument('--portable-receipt', action='store_true', help='write a public path-template receipt; default receipt is local-only')
p.add_argument('--extra-source', type=Path, action='append', default=[])
p.add_argument('--moc-header', type=Path, action='append', default=[])
p.add_argument('--resource-qrc', type=Path, action='append', default=[])
p.add_argument('--generated-qt-build', type=Path,
               help='target Qt configuration supplying generated headers omitted by a release bundle')
p.add_argument('--extra-archive', type=Path, action='append', default=[],
               help='additional target archive to include in the final link group')
a=p.parse_args()
source,sdk,qt,qs,core,host,binutils,out=[getattr(a,n).resolve() for n in
    ('source','sdk','qt_build','qt_source','core_build','host_qt','binutils','output')]
extra_archives=[p.resolve() for p in a.extra_archive]
here=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def host_tool(name):
    path=host/'libexec'/name
    if not path.is_file() and Path(str(path)+'.exe').is_file():
        path=Path(str(path)+'.exe')
    return path
sdk_metadata=json.loads((sdk/'manifest.json').read_text())
sdk_release=sdk/'release.json'
release_drift=set()
if 'artifacts' in sdk_metadata:
    sdk_files=sdk_metadata['artifacts']
else:
    release=json.loads(sdk_release.read_text())
    if release.get('version')!='0.0.2-1103' or release.get('system_build_id')!=sdk_metadata.get('build_id'):
        raise SystemExit('SDK release/system identity mismatch')
    sdk_files=release.get('sdk_binding',{}).get('packaged',{}).get('files',{})
    if not sdk_files: raise SystemExit('SDK has no published file binding')
    # This release archive has four known post-packaging metadata/document edits.
    # Keep the exception exact; every other bound file remains hash-verified.
    release_drift={'DEVELOPING.md','docs/releases/SDK_DEVELOPING.md',
                   'licenses/open_items.json','tools/xos_app.py'}
    missing=release_drift-set(sdk_files)
    if missing: raise SystemExit('SDK drift allowlist does not match release binding: '+', '.join(sorted(missing)))
    required={'crt0_posix.o','user.ld','lib/libxos.a','lib/libc.a','lib/libm.a',
              'cpp/lib/libstdc++.a','cpp/lib/libsupc++.a','cpp/lib/libgcc.a'}
    if required-set(sdk_files): raise SystemExit('SDK binding omits required runtime files')
    for rel in sorted(release_drift):
        print('Known release SDK binding drift (not used for Qt link): '+rel,file=sys.stderr)
for rel,h in sdk_files.items():
    if rel in release_drift: continue
    if sha(sdk/rel)!=h: raise SystemExit('SDK mismatch: '+rel)
if core != qt: raise SystemExit('Widgets must use Core/Gui from the same build')
expected=sha(core/'lib/libQt6Core.a')
cache_path=qt/'CMakeCache.txt'
asset_manifest=qt.parent/'asset_manifest.json'
if cache_path.is_file():
    cache=cache_path.read_text()
    if 'FEATURE_widgets:BOOL=ON' not in cache: raise SystemExit('Widgets feature not enabled')
    if '-I'+(sdk/'include').as_posix() not in cache.replace('\\','/'):
        raise SystemExit('Qt/SDK configuration mismatch')
    qt_inputs=[cache_path]
else:
    if not asset_manifest.is_file(): raise SystemExit('Qt build cache or release asset manifest required')
    assets=json.loads(asset_manifest.read_text())
    if assets.get('qt_version')!='6.8.3': raise SystemExit('Qt release version mismatch')
    for key,h in assets.get('files',{}).items():
        if key.startswith(qt.name+'/') and sha(qt.parent/key)!=h:
            raise SystemExit('Qt release asset mismatch: '+key)
    if not assets.get('files'): raise SystemExit('Qt release manifest has no file bindings')
    qt_inputs=[asset_manifest]
out.parent.mkdir(parents=True,exist_ok=True)
overlay=out.parent/'qt_header_overlay'
shutil.copytree(qt/'include',overlay,dirs_exist_ok=True)
overlay_headers=[]
overlay_targets=[]
generated_root=(a.generated_qt_build.resolve() if a.generated_qt_build else qt)/'src'
absolute_forwarder=re.compile(r'^#include "([A-Za-z]:/[^"\r\n]+)"',re.M)
for header in (qt/'include').rglob('*'):
    if not header.is_file(): continue
    try: contents=header.read_text()
    except (UnicodeError,OSError): continue
    absolute=absolute_forwarder.search(contents)
    if absolute:
        target=Path(absolute.group(1))
        roots=[qs,qt]
        if a.generated_qt_build: roots.append(a.generated_qt_build.resolve())
        for root in roots:
            try: relative_source=target.relative_to(root)
            except ValueError: continue
            resolved=(root/relative_source).resolve()
            if not resolved.is_file(): raise SystemExit('Qt forwarded header target missing: '+str(resolved))
            destination=overlay/header.relative_to(qt/'include')
            destination.parent.mkdir(parents=True,exist_ok=True)
            relative_target=Path(os.path.relpath(resolved,destination.parent)).as_posix()
            destination.write_text(contents.replace(absolute.group(0),'#include "'+relative_target+'"'))
            overlay_headers.append(destination);overlay_targets.append(resolved)
            break
        else:
            relative_source=None
        if relative_source is not None: continue
    line=re.search(r'^#include "([^"\r\n]+)"',contents,re.M)
    if line:
        roots=[qs,qt]
        if a.generated_qt_build: roots.append(a.generated_qt_build.resolve())
        for root in roots:
            anchor=root.name+'/'
            if anchor not in line.group(1): continue
            target=(root/line.group(1).split(anchor,1)[1]).resolve()
            if not target.is_file(): raise SystemExit('Qt forwarded header target missing: '+str(target))
            destination=overlay/header.relative_to(qt/'include')
            destination.parent.mkdir(parents=True,exist_ok=True)
            relative_target=Path(os.path.relpath(target,destination.parent)).as_posix()
            destination.write_text(contents.replace(line.group(0),'#include "'+relative_target+'"'))
            overlay_headers.append(destination);overlay_targets.append(target)
            break
        else:
            target=None
        if target is not None: continue
        source_suffix=re.search(r'(?:^|/)(src/[^"\r\n]+)$',line.group(1))
        if source_suffix:
            relative_source=Path(source_suffix.group(1))
            for root in (qt,qs):
                candidate=(root/relative_source).resolve()
                if not candidate.is_file(): continue
                destination=overlay/header.relative_to(qt/'include')
                destination.parent.mkdir(parents=True,exist_ok=True)
                relative_target=Path(os.path.relpath(candidate,destination.parent)).as_posix()
                destination.write_text(contents.replace(line.group(0),'#include "'+relative_target+'"'))
                overlay_headers.append(destination);overlay_targets.append(candidate)
                break
            else:
                candidate=None
            if candidate is not None: continue
    # Recognize historical Qt source/build layouts without binding a host home.
    match=re.search(r'^#include "[^"\r\n]*/(qtbase-6\.8\.3-gui|widgets2?)/src/([^"\r\n]+)"',contents,re.M)
    if not match: continue
    root=(qs/'src' if match.group(1)=='qtbase-6.8.3-gui' else generated_root).resolve()
    target=(root/match.group(2)).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise SystemExit('Qt forwarded header target missing or outside source root')
    destination=overlay/header.relative_to(qt/'include')
    destination.parent.mkdir(parents=True,exist_ok=True)
    relative_target=Path(os.path.relpath(target,destination.parent)).as_posix()
    destination.write_text(contents.replace(match.group(0), '#include "'+relative_target+'"'))
    overlay_headers.append(destination);overlay_targets.append(target)
for name in ('moc','rcc'):
    if '6.8.3' not in subprocess.check_output([host_tool(name),'-v'],stderr=subprocess.STDOUT,text=True):
        raise SystemExit('Host tool version mismatch')
commands=[]
def run(cmd):
    commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
font=qs/'src/3rdparty/wasm/DejaVuSans.ttf'
qrc=out.parent/'xos_fonts.qrc'
asset=here/'aurora/assets/aurora.bmp'
wallpaper=here/'aurora/assets/curvive_wallpaper.bmp'
qrc.write_text('<RCC><qresource prefix="/xos"><file alias="DejaVuSans.ttf">'+str(font)+
               '</file><file alias="aurora-wallpaper.bmp">'+str(wallpaper)+
               '</file></qresource></RCC>\n')
run([host_tool('rcc'),'--name','xos_fonts',qrc,'-o',out.parent/'qrc_xos_fonts.cpp'])
flags=['-std=c++17','-O2','-fPIC','-mno-red-zone','-fno-stack-protector','-ftls-model=local-exec',
       '-D__XOS__','-DXOS_THREADED_RUNTIME','-D_POSIX_C_SOURCE=200809L','-D_POSIX_THREADS=1','-DQT_CORE_LIB','-DQT_GUI_LIB',
       '-DQT_WIDGETS_LIB','-DQT_NO_DEBUG','-DQT_STATICPLUGIN','-nostdinc++','-B'+str(binutils)+'/',
       '-I'+str(here.parents[2]/'src/shared/include'),'-I'+str(here.parents[2]/'src/user/include'),
       '-I'+str(here/'aurora'),
       '-I'+str(sdk/'cpp/include'),'-I'+str(sdk/'cpp/include/x86_64-elf'),
       '-I'+str(sdk/'cpp/include/c++/16.2.0'),'-I'+str(sdk/'cpp/include/c++/16.2.0/x86_64-unknown-elf'),
       '-I'+str(sdk/'include'),
       '-I'+str(overlay),'-I'+str(overlay/'QtCore'),'-I'+str(overlay/'QtGui'),'-I'+str(overlay/'QtWidgets'),
       '-I'+str(overlay/'QtCore/6.8.3/QtCore'),'-I'+str(overlay/'QtGui/6.8.3/QtGui'),
       '-I'+str(qt/'include'),'-I'+str(qt/'include/QtCore'),'-I'+str(qt/'include/QtGui'),'-I'+str(qt/'include/QtWidgets'),
       '-I'+str(overlay/'QtCore/6.8.3'),'-I'+str(qt/'include/QtCore/6.8.3'),'-I'+str(qt/'include/QtCore/6.8.3/QtCore'),
       '-I'+str(overlay/'QtGui/6.8.3'),'-I'+str(qt/'include/QtGui/6.8.3'),'-I'+str(qt/'include/QtGui/6.8.3/QtGui'),
       '-I'+str(here/'runtime'),'-I'+str(out.parent)]
flags += ['-I'+p.resolve().parent.as_posix() for p in a.extra_source]
run([host_tool('moc'),*[f for f in flags if f.startswith(('-I','-D'))],here/'qpa/qxos.cpp','-o',out.parent/'qxos.moc'])
cxx=shutil.which('x86_64-elf-g++');ar=shutil.which('x86_64-elf-ar')
aurora=out.parent/'libXosAurora.a'
run([sys.executable,here/'build_aurora.py','--sdk',sdk,'--qt-build',qt,'--host-qt',host,'--binutils',binutils,'--include-overlay',overlay,'--output',aurora])
objs=[]
additional_sources = [p.resolve() for p in a.extra_source]
for i, header in enumerate(a.moc_header):
    generated = out.parent / ('moc_shell_' + str(i) + '.cpp')
    run([host_tool('moc'), *[f for f in flags if f.startswith(('-I','-D'))], header.resolve(), '-o', generated])
    additional_sources.append(generated)
for i, resource in enumerate(a.resource_qrc):
    generated = out.parent / ('qrc_shell_' + str(i) + '.cpp')
    run([host_tool('rcc'), '--compress-algo', 'zlib', '--name', 'shell_' + str(i), resource.resolve(), '-o', generated])
    additional_sources.append(generated)
for name,src in [('qxos',here/'qpa/qxos.cpp'),('fonts',out.parent/'qrc_xos_fonts.cpp'),('demo',source)] + [('extra_'+str(i), p) for i,p in enumerate(additional_sources)]:
    obj=out.parent/(name+'.o');run([cxx,*flags,'-c',src,'-o',obj]);objs.append(obj)
plugin=out.parent/'libQXosIntegrationPlugin.a'
# MSYS ar can retain duplicate members for Windows backslash paths. Recreate
# this generated archive so an earlier QPA object cannot win during linking.
plugin.unlink(missing_ok=True)
run([ar,'rcs',plugin.as_posix(),objs[0].as_posix()])
archives=[qt/'lib/libQt6Widgets.a',qt/'lib/libQt6Gui.a',core/'lib/libQt6Core.a',core/'lib/libQt6BundledPcre2.a',
          core/'lib/libQt6BundledZLIB.a',qt/'lib/libQt6BundledFreetype.a',qt/'lib/libQt6BundledHarfbuzz.a']
# Gui's shader resource is emitted as a separate CMake object in static builds.
resources=list((qt/'src/gui').glob('CMakeFiles/Gui_resources_*.dir/.rcc/*.o')) + list((qt/'src/widgets').glob('CMakeFiles/Widgets_resources_*.dir/.rcc/*.o'))
run([cxx,'-B'+str(binutils)+'/','-nostdlib','-static','-no-pie',
     '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
     *['-Wl,--wrap='+n for n in a.wrap],'-T',sdk/'user.ld',sdk/'crt0_posix.o',*objs[1:],*resources,'-Wl,--start-group',plugin,aurora,*archives,
     *extra_archives,
     '-Wl,--whole-archive',sdk/'lib/libxos.a','-Wl,--no-whole-archive',sdk/'cpp/lib/libstdc++.a',
     sdk/'cpp/lib/libsupc++.a',sdk/'lib/libc.a',sdk/'lib/libm.a',sdk/'cpp/lib/libgcc.a','-Wl,--end-group','-o',out])
config_summary=qt/'config.summary'
if config_summary.is_file():qt_inputs.append(config_summary)
overlay_files=[f for f in overlay.rglob('*') if f.is_file()]
inputs=[asset,wallpaper,aurora,*extra_archives,*sorted((here/'aurora').glob('*.*')),*sorted((here/'editor').glob('*.hpp')),here/'editor/main.cpp',*qt_inputs,*overlay_files,*overlay_targets,*sorted((here/'patches').glob('*.patch')),*sorted((here/'runtime').glob('*.*')),source,here/'qpa/qxos.cpp',here/'qpa/xos.json',Path(__file__),font,sdk/'manifest.json',*([sdk_release] if sdk_release.is_file() else []),*archives,*resources,plugin]
receipt={'commands':commands,'inputs':{str(p):sha(p) for p in inputs},'elf_sha256':sha(out),
         'qtcore_sha256':expected,'host_tools':{n:sha(host_tool(n)) for n in ('moc','rcc')}}
receipt['inputs'].update({str(p.resolve()): sha(p) for p in [*a.extra_source, *a.moc_header, *a.resource_qrc, *additional_sources]})
mappings=[('XOS_SDK_PREFIX',sdk),('XOS_BUILD_DIR',qt),('XOS_QT_SOURCE',qs),('XOS_HOST_QT',host),('XOS_BINUTILS',binutils),('XOS_ARTIFACT_DIR',out.parent),('XOS_CXX',cxx),('XOS_AR',ar),('XOS_PYTHON',sys.executable)]
if a.portable_receipt:
    receipt['commands_kind']='templates; execution uses the original runtime arguments'
    receipt=portable(receipt,mappings,strict=True)
out.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Built real Qt Widgets XOS ELF:',out)
