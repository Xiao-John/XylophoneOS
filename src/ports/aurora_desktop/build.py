#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the single-Surface desktop, session parent, SDK Studio and gap probe."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk','qt-build','qt-source','host-qt','binutils','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    args=[]
    for name in ('sdk','qt-build','qt-source','host-qt','binutils'):
        args += ['--'+name,str(getattr(a,name.replace('-','_')).resolve())]
    args+=['--core-build',str(a.qt_build.resolve())]
    commands=[]
    def run(cmd):
        commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
    for name,source in [('desktop',ROOT/'src/ports/aurora_desktop/main.cpp'),
                        ('studio',ROOT/'tests/fixtures/qt6/aurora_v2_studio.cpp'),
                        ('semantics',ROOT/'tests/fixtures/qt6/aurora_semantics.cpp'),
                        ('render',ROOT/'tests/fixtures/qt6/aurora_render_probe.cpp')]:
        run([sys.executable,ROOT/'src/ports/qt6/build_widgets_fixture.py',*args,
             '--source',source,'--output',out/name/(name+'.elf')])
    for name,source in [('session',ROOT/'src/ports/aurora_desktop/session.cpp'),
                        ('compositor_gap',ROOT/'tests/fixtures/qt6/compositor_gap.cpp')]:
        target=out/(name+'.elf')
        run([sys.executable,a.sdk.resolve()/'compile.py',source,'-o',target])
        target.with_suffix('.receipt.json').write_text(json.dumps({
            'elf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                      [source,a.sdk.resolve()/'manifest.json',Path(__file__).resolve()]}
        },indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
if __name__=='__main__':main()
