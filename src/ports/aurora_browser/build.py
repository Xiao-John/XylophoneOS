#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build pinned liteHTML/Gumbo and Aurora browser against a matching static XOS Qt SDK."""
import argparse,hashlib,json,re,shutil,subprocess,sys,tarfile
from pathlib import Path
here=Path(__file__).resolve().parent;root=here.parents[2];qtport=root/'src/ports/qt6'
p=argparse.ArgumentParser(description=__doc__)
for name in ('sdk','qt-build','qt-source','host-qt','binutils','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();sdk,qt,qs,host,binutils,out=[getattr(a,k).resolve() for k in ('sdk','qt_build','qt_source','host_qt','binutils','output')]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();commands=[]
def run(cmd):
 commands.append([str(x) for x in cmd]);subprocess.run(cmd,check=True)
for rel,h in json.loads((sdk/'manifest.json').read_text())['artifacts'].items():assert sha(sdk/rel)==h,rel
cache=(qt/'CMakeCache.txt').read_text();assert 'FEATURE_widgets:BOOL=ON' in cache;assert '-I'+str(sdk/'include') in cache
lock=json.loads((here/'source_lock.json').read_text());archive=here/lock['archive'];assert sha(archive)==lock['archive_sha256']
work=out.parent;work.mkdir(parents=True,exist_ok=True);source=work/'litehtml-0.9'
if not source.exists():
 with tarfile.open(archive) as tar:tar.extractall(work,filter='data')
# Source tree manifest rejects edited/mixed extraction as well as stale objects.
for rel,h in lock['source_sha256'].items():assert sha(source/rel)==h,rel
# Keep the pinned original pristine; patch a private build copy deterministically.
pristine=source;source=work/'litehtml-ssg';shutil.copytree(pristine,source,dirs_exist_ok=True)
patch=here/'patches/0001_readonly_render_fragments.patch'
run(['patch','-p1','-i',patch,'-d',source])
cxx=shutil.which('x86_64-elf-g++');cc=shutil.which('x86_64-elf-gcc');ar=shutil.which('x86_64-elf-ar');assert cxx and cc and ar
base=['-O2','-fPIC','-mno-red-zone','-fno-stack-protector','-ftls-model=local-exec','-D__XOS__','-DXOS_THREADED_RUNTIME','-D_POSIX_C_SOURCE=200809L','-B'+str(binutils)+'/']
cpp=['-std=c++17','-nostdinc++','-I'+str(sdk/'cpp/include'),'-I'+str(sdk/'cpp/include/x86_64-elf')]
incs=['-I'+str(source/'include'),'-I'+str(source/'include/litehtml'),'-I'+str(source/'src'),'-I'+str(source/'src/gumbo/include'),'-I'+str(source/'src/gumbo/include/gumbo')]
objs=[]
for src in sorted((source/'src').glob('*.cpp'))+sorted((source/'src/gumbo').glob('*.c')):
 obj=work/(('gumbo_' if src.suffix=='.c' else 'html_')+src.stem+'.o');run([cc if src.suffix=='.c' else cxx,*base,*(cpp if src.suffix=='.cpp' else ['-std=c99']),'-I'+str(sdk/'include'),*incs,'-c',src,'-o',obj]);objs.append(obj)
engine=work/'liblitehtml.a';run([ar,'rcs',engine,*objs])
qrc=work/'fonts.qrc';font=qs/'src/3rdparty/wasm/DejaVuSans.ttf';qrc.write_text('<RCC><qresource prefix="/xos"><file alias="DejaVuSans.ttf">'+str(font)+'</file></qresource></RCC>')
run([host/'libexec/rcc','--name','xos_fonts',qrc,'-o',work/'fonts.cpp'])
flags=[*base,*cpp,'-I'+str(sdk/'include'),*incs,'-DQT_CORE_LIB','-DQT_GUI_LIB','-DQT_WIDGETS_LIB','-DQT_NO_DEBUG','-DQT_STATICPLUGIN',*['-I'+str(qt/'include'/p) for p in ('','QtCore','QtGui','QtWidgets','QtCore/6.8.3','QtCore/6.8.3/QtCore','QtGui/6.8.3','QtGui/6.8.3/QtGui')],'-I'+str(qtport/'runtime'),'-I'+str(work)]
run([host/'libexec/moc',*[f for f in flags if f.startswith(('-I','-D'))],qtport/'qpa/qxos.cpp','-o',work/'qxos.moc'])
appobjs=[]
for name,src in [('qxos',qtport/'qpa/qxos.cpp'),('fonts',work/'fonts.cpp'),('browser',here/'main.cpp')]:
 obj=work/(name+'.o');run([cxx,*flags,'-c',src,'-o',obj]);appobjs.append(obj)
aurora=work/'libXosAurora.a';run([sys.executable,qtport/'build_aurora.py','--sdk',sdk,'--qt-build',qt,'--host-qt',host,'--binutils',binutils,'--output',aurora])
archives=[qt/'lib'/('lib'+n+'.a') for n in ('Qt6Widgets','Qt6Gui','Qt6Core','Qt6BundledPcre2','Qt6BundledZLIB','Qt6BundledFreetype','Qt6BundledHarfbuzz')]
resources=list((qt/'src/gui').glob('CMakeFiles/Gui_resources_*.dir/.rcc/*.o'))+list((qt/'src/widgets').glob('CMakeFiles/Widgets_resources_*.dir/.rcc/*.o'))
run([cxx,'-B'+str(binutils)+'/','-nostdlib','-static','-no-pie','-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096','-T',sdk/'user.ld',sdk/'crt0_posix.o',*appobjs,*resources,'-Wl,--start-group',aurora,engine,*archives,'-Wl,--whole-archive',sdk/'lib/libxos.a','-Wl,--no-whole-archive',sdk/'cpp/lib/libstdc++.a',sdk/'cpp/lib/libsupc++.a',sdk/'lib/libc.a',sdk/'lib/libm.a',sdk/'cpp/lib/libgcc.a','-Wl,--end-group','-o',out])
inputs=[Path(__file__),here/'source_lock.json',archive,patch,*sorted(here.glob('*.hpp')),here/'main.cpp',font,sdk/'manifest.json',qt/'CMakeCache.txt',qtport/'qpa/qxos.cpp',*sorted((qtport/'aurora').glob('*.hpp')),*sorted((qtport/'aurora').glob('*.cpp')),aurora,engine,*archives,*resources,*[sdk/rel for rel in ('user.ld','crt0_posix.o','lib/libxos.a','lib/libc.a','lib/libm.a','cpp/lib/libstdc++.a','cpp/lib/libsupc++.a','cpp/lib/libgcc.a')]]
receipt={'commands':commands,'inputs':{str(p):sha(p) for p in inputs},'elf_sha256':sha(out),'engine_archive_sha256':sha(engine),'engine_commit':lock['commit'],'tools':{str(t):{'sha256':sha(Path(t)),'version':subprocess.check_output([t,'--version'],text=True).splitlines()[0]} for t in (cxx,cc,ar)},'source_manifest':lock['source_sha256']};out.with_suffix('.receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('Built real XOS Aurora browser',out)
