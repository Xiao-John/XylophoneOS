#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the single-Surface desktop, session parent, SDK Studio and gap probe."""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from xos_app import tree_receipt
from xypm_format import require

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk','qt-build','qt-source','host-qt','binutils','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--products-only', action='store_true', help='build the two Mobius package executables')
    a=p.parse_args(); out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    sdk = a.sdk.resolve()
    sdk_tree_digest, _ = tree_receipt(sdk)
    args=[]
    for name in ('sdk','qt-build','qt-source','host-qt','binutils'):
        args += ['--'+name,str(getattr(a,name.replace('-','_')).resolve())]
    args+=['--core-build',str(a.qt_build.resolve())]
    commands=[]
    def run(cmd):
        commands.append(list(map(str,cmd)));subprocess.run(cmd,check=True)
    widgets = [('desktop', ROOT / 'src/ports/aurora_desktop/main.cpp')]
    native = [('session', ROOT / 'src/ports/aurora_desktop/session.cpp')]
    if not a.products_only:
        fixtures = ROOT / 'tests/fixtures/qt6'
        widgets.extend([('studio', fixtures / 'aurora_v2_studio.cpp'),
                        ('semantics', fixtures / 'aurora_semantics.cpp'),
                        ('render', fixtures / 'aurora_render_probe.cpp')])
        native.append(('compositor_gap', fixtures / 'compositor_gap.cpp'))
    for name,source in widgets:
        run([sys.executable,ROOT/'src/ports/qt6/build_widgets_fixture.py',*args,
             '--bind-sdk-tree','--source',source,'--output',out/name/(name+'.elf')])
    for name,source in native:
        target=out/(name+'.elf')
        run([sys.executable,sdk/'compile.py',source,'-o',target])
        require(tree_receipt(sdk)[0] == sdk_tree_digest, 'SDK changed during desktop build')
        target.with_suffix('.receipt.json').write_text(json.dumps({
            'elf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'sdk_tree_sha256':sdk_tree_digest,
            'inputs':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                      [source,sdk/'manifest.json',Path(__file__).resolve()]}
        },indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
if __name__=='__main__':main()
