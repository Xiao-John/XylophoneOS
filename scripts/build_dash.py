# SPDX-License-Identifier: Apache-2.0
"""Explicit, isolated dash C2 cross build against a frozen XOS SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import shlex

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT/'src/ports/dash'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=ROOT/'build/sdk')
    parser.add_argument('--archive', type=Path, default=ROOT/'src/ports/dash/upstream/dash-0.5.13.5.tar.gz')
    a = parser.parse_args()
    if not a.archive.exists():
        parser.error(f'dash archive not found: {a.archive}')
    sdk, archive = a.sdk.resolve(strict=True), a.archive.resolve(strict=True)
    lock = json.loads((PORT/'source_lock.json').read_text())
    if sha(archive) != lock['sha256']: parser.error('dash archive hash mismatch')
    inputs = {str(p.relative_to(ROOT)):sha(p) for p in sorted(PORT.rglob('*')) if p.is_file()}
    inputs['scripts/build_dash.py'] = sha(__file__)
    inputs.update({'sdk/'+str(p.relative_to(sdk)):sha(p) for p in sorted(sdk.rglob('*')) if p.is_file()})
    key = hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    work = ROOT/'.cache/xos_seed/dash'/key
    work.mkdir(parents=True,exist_ok=True)
    source = work/'source'
    if not source.exists():
        source.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if '..' in parts or Path(member.name).is_absolute() or member.issym() or member.islnk():
                    raise ValueError('unsafe source archive member')
                member.name = str(Path(*parts[1:]))
                if member.name != '.':
                    try:
                        tar.extract(member,source,filter='data')
                    except TypeError:
                        tar.extract(member,source)
        if not (source/'configure').is_file():
            raise SystemExit(f'dash extraction produced no configure under {source}')
        for patch in sorted((PORT/'patches').glob('*.patch')):
            subprocess.run(['patch','-p1','-i',str(patch)],cwd=source,check=True,stdout=subprocess.DEVNULL)
        for local, upstream in (('jobs_xos.c','jobs.c'),('signals_xos.c','trap.c')):
            shutil.copyfile(PORT/local,source/'src'/upstream)
        with (source/'src/eval.c').open('a') as stream:stream.write('\n'+(PORT/'admission_xos.c').read_text())
    build = work/'build';build.mkdir(exist_ok=True)
    cc = os.environ.get('XOS_CC',shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc')
    cxx = os.environ.get('XOS_CXX',shutil.which('x86_64-elf-g++') or 'x86_64-elf-g++')
    target_tools = work/'target_tools'
    target_tools.mkdir(exist_ok=True)
    for name in ('as', 'ld'):
        link = target_tools/name
        if not link.exists(): link.symlink_to(Path(shutil.which('x86_64-elf-'+name)).resolve())
    flags = ['-B'+str(target_tools)+'/', '-O2','-mno-red-zone','-fno-pie','-fno-pic','-fno-stack-protector','-ffunction-sections','-fdata-sections','-isystem',str(ROOT/'src/user/include')]
    bridge = work/'console_xos.o'
    subprocess.run([cxx,*flags,'-fno-exceptions','-fno-rtti','-isystem',str(sdk/'include'),'-c',str(PORT/'console_xos.cpp'),'-o',str(bridge)],check=True)
    libs = [str(bridge),'-Wl,--start-group',*[str(sdk/'lib'/n) for n in ('libxos.a','libxos_loader.a','libc.a','libm.a')],subprocess.check_output([cc,'-print-libgcc-file-name'],text=True).strip(),'-Wl,--end-group']
    env = dict(os.environ,CC=cc,CC_FOR_BUILD=shutil.which('clang') or 'cc',
               CFLAGS=shlex.join(flags),CPPFLAGS=shlex.join(['-DJOBS=0','-include',str(PORT/'xos_profile.h'),'-isystem',str(sdk/'include')]),
               LDFLAGS=shlex.join(['-nostdlib','-static','-no-pie','-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0_posix.o')]),LIBS=shlex.join(libs))
    def run(args,name):
        with (work/name).open('w') as log:
            result = subprocess.run(args,cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            print((work/name).read_text()[-7000:]);raise SystemExit(result.returncode)
    if not (build/'Makefile').exists():
        run([str(source/'configure'),'--build=aarch64-apple-darwin','--host=x86_64-unknown-elf','--without-libedit','--disable-glob','--disable-tee','--disable-memfd-create'],'configure.log')
    run(['make','-j2'],'make.log')
    elf = build/'src/dash'
    result = {'profile':'dash_c2','version':lock['version'],'elf':str(elf.relative_to(ROOT)),'sha256':sha(elf),'bytes':elf.stat().st_size,'inputs':inputs,'status':'built_not_run'}
    (work/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='inputs'}))


if __name__=='__main__':main()
