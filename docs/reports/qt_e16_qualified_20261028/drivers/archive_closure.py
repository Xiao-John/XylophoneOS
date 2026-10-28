import subprocess,json
from pathlib import Path
sdk=Path('../XylophoneOS-qt6-e15/build/qt_e15/frozen_sdk');core=Path('../XylophoneOS-qt6-e15/build/qt_e15/final_qt/lib');gui=Path('build/qt_e16/gui/lib')
archives=[gui/'libQt6Gui.a',gui/'libQt6BundledFreetype.a',gui/'libQt6BundledHarfbuzz.a',core/'libQt6Core.a',core/'libQt6BundledPcre2.a',core/'libQt6BundledZLIB.a',sdk/'lib/libxos.a',sdk/'cpp/lib/libstdc++.a',sdk/'cpp/lib/libsupc++.a',sdk/'lib/libc.a',sdk/'lib/libm.a',sdk/'cpp/lib/libgcc.a',sdk/'crt0_posix.o',Path('build/qt_e16/qualified_app/libQXosIntegrationPlugin.a')]
defined=set();undefined=set()
for archive in archives:
 output=subprocess.check_output(['x86_64-elf-nm','-g',str(archive)],text=True,stderr=subprocess.DEVNULL)
 for line in output.splitlines():
  fields=line.split()
  if len(fields)>=2:
   kind,sym=fields[-2:]
   if kind=='U':undefined.add(sym)
   elif len(kind)==1 and kind.isalpha() and kind not in ('w','v'):defined.add(sym)
missing=sorted(undefined-defined)
Path('build/qt_e16/qtgui_archive_unresolved.txt').write_text('\n'.join(missing)+'\n')
print(missing)
