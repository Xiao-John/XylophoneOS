#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile a QtCore fixture with the selected QtBase build and threading SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from ssg_public_paths import portable

p = argparse.ArgumentParser(description=__doc__)
for name in ('source', 'qrc', 'sdk', 'qt_build', 'host_qt', 'binutils', 'output'):
    p.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
p.add_argument('--portable-receipt', action='store_true', help='write a public path-template receipt; default receipt is local-only')
a = p.parse_args()
source, qrc, sdk, qt, host, binutils, out = [getattr(a, n).resolve() for n in
    ('source', 'qrc', 'sdk', 'qt_build', 'host_qt', 'binutils', 'output')]
manifest = json.loads((sdk / 'manifest.json').read_text())
for rel, expected in manifest['artifacts'].items():
    if hashlib.sha256((sdk / rel).read_bytes()).hexdigest() != expected:
        raise SystemExit('SDK artifact hash mismatch: ' + rel)
for name in ('moc', 'rcc'):
    version = subprocess.check_output([str(host / 'libexec' / name), '-v'], stderr=subprocess.STDOUT, text=True)
    if '6.8.3' not in version:
        raise SystemExit('host tool version mismatch: ' + version)
if not (qt / 'lib/libQt6Core.a').is_file():
    raise SystemExit('missing target QtCore archive')
out.parent.mkdir(parents=True, exist_ok=True)
obj = out.with_suffix('.o')
rcc_source = out.with_name(out.stem + '_qrc.cpp')
rcc_obj = out.with_name(out.stem + '_qrc.o')
commands = []
def run(cmd):
    commands.append([str(x) for x in cmd])
    subprocess.run(cmd, check=True)
if '#include "core_smoke.moc"' in source.read_text():
    run([host/'libexec/moc', source, '-o', out.parent/'core_smoke.moc'])
run([host/'libexec/rcc', '--name', 'probe', qrc, '-o', rcc_source])
cxx = shutil.which('x86_64-elf-g++')
if not cxx: raise SystemExit('missing x86_64-elf-g++')
flags = ['-std=c++17', '-O2', '-fPIC', '-mno-red-zone', '-fno-stack-protector',
         '-ftls-model=local-exec', '-D__XOS__', '-DXOS_THREADED_RUNTIME',
         '-D_POSIX_C_SOURCE=200809L', '-DQT_CORE_LIB', '-DQT_NO_DEBUG', '-nostdinc++',
         '-I'+str(sdk/'cpp/include'), '-I'+str(sdk/'cpp/include/x86_64-elf'),
         '-I'+str(sdk/'include'), '-I'+str(qt/'include'), '-I'+str(qt/'include/QtCore'),
         '-I'+str(out.parent), '-B'+str(binutils)+'/']
run([cxx, *flags, '-c', source, '-o', obj])
run([cxx, *flags, '-c', rcc_source, '-o', rcc_obj])
run([cxx, '-B'+str(binutils)+'/', '-nostdlib', '-static', '-no-pie',
     '-Wl,--gc-sections,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
     '-T', sdk/'user.ld', sdk/'crt0_posix.o', obj, rcc_obj, '-Wl,--start-group',
     qt/'lib/libQt6Core.a', qt/'lib/libQt6BundledPcre2.a', qt/'lib/libQt6BundledZLIB.a',
     '-Wl,--whole-archive', sdk/'lib/libxos.a', '-Wl,--no-whole-archive',
     sdk/'cpp/lib/libstdc++.a', sdk/'cpp/lib/libsupc++.a', sdk/'lib/libc.a',
     sdk/'lib/libm.a', sdk/'cpp/lib/libgcc.a', '-Wl,--end-group', '-o', out])
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
resource_files = {}
for element in ET.parse(qrc).iter('file'):
    path = (qrc.parent / (element.text or '')).resolve(strict=True)
    if qrc.parent not in path.parents:
        raise SystemExit('resource file outside qrc directory: ' + str(path))
    resource_files[str(path.relative_to(qrc.parent))] = sha(path)
receipt = {'resource_files': resource_files, 'source': str(source), 'source_sha256': sha(source), 'qrc_sha256': sha(qrc),
           'sdk_manifest_sha256': sha(sdk/'manifest.json'), 'qtcore_sha256': sha(qt/'lib/libQt6Core.a'),
           'elf_sha256': sha(out), 'commands': commands}
mappings = [('XOS_SDK_PREFIX',sdk),('XOS_BUILD_DIR',qt),('XOS_HOST_QT',host),
            ('XOS_BINUTILS',binutils),('XOS_ARTIFACT_DIR',out.parent),('XOS_CXX',cxx)]
if a.portable_receipt:
    receipt['commands_kind'] = 'templates; execution uses the original runtime arguments'
    receipt = portable(receipt,mappings,strict=True)
out.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
print('Built target fixture:', out)
