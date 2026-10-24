# SPDX-License-Identifier: Apache-2.0
"""Package the frozen, accepted XOS image/SDK and a new offline development disk."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.0.1-1024'
PREFIX = 'xylophoneos_revival_' + VERSION


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def copy_notices(destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('LICENSE', 'NOTICE'):
        shutil.copyfile(ROOT/name, destination/name)
    shutil.copyfile(ROOT/'src/third_party/newlib/COPYING.NEWLIB', destination/'COPYING.NEWLIB')
    shutil.copytree(ROOT/'licenses', destination/'licenses', dirs_exist_ok=True)
    for component in ('gcc', 'binutils'):
        shutil.copytree(ROOT/'src/ports'/component/'upstream', destination/'licenses'/component, dirs_exist_ok=True)


def archive(source, output):
    with tarfile.open(output, 'w:gz', compresslevel=1) as tar:
        tar.add(source, arcname=source.name)
    print(output, output.stat().st_size, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release-dir', type=Path, default=ROOT/'build/releases'/VERSION)
    a = p.parse_args()
    out = a.release_dir.resolve(strict=True)
    if ROOT/'build/releases' not in out.parents:
        p.error('use a dedicated build/releases directory')
    system = json.loads((out/'system_manifest.json').read_text())
    if sha(out/'xos.img') != system['artifacts']['xos.img']['sha256']:
        p.error('frozen boot image differs from accepted manifest')
    seed = json.loads((ROOT/'build/cpp_bundle/seed_manifest.json').read_text())
    sysroot = json.loads((ROOT/'build/cpp_bundle/sysroot_manifest.json').read_text())
    from seed_preflight import validate_bundle
    result = validate_bundle(seed, ROOT, sysroot, ROOT, required_tools=('gcc','cc1','g++','cc1plus','as','ld','ar','ranlib'))
    if not result.ok:
        raise ValueError(result.diagnostics)
    image_dir, sdk_dir = out/(PREFIX+'_images'), out/(PREFIX+'_sdk')
    image_dir.mkdir(exist_ok=True)
    sdk_dir.mkdir(exist_ok=True)
    disk = image_dir/'work_disk.img'
    if disk.exists():
        p.error('refuse to overwrite release work disk')
    from make_work_disk import create_fat32
    create_fat32(disk, 2048)
    helper = ROOT/'build/work_disk_host'
    if not helper.is_file():
        p.error('build/work_disk_host must already be prepared; do not rebuild shared tools')
    entries = seed['install_files'] + sysroot['files']
    directories = {'/src','/out','/tmp'}
    for entry in entries:
        source = ROOT/entry['path']
        if sha(source) != entry['sha256']:
            raise ValueError('input changed: '+entry['path'])
        parent = Path(entry['guest_path']).parent
        while str(parent) != '/':
            directories.add(parent.as_posix()); parent = parent.parent
    def transfer(op, path, source=None):
        command = [str(helper), str(disk), op, path]
        if source is not None:command.append(str(source))
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
    for directory in sorted(directories, key=lambda path:(path.count('/'),path)):
        transfer('mkdir', directory)
    for entry in entries:
        transfer('import', entry['guest_path'], ROOT/entry['path'])
    examples = {
        'hello.c': '#include <stdio.h>\nint main(void) { puts("Happy 1024 from XOS C!"); return 0; }\n',
        'hello.cpp': '#include <cstdio>\n#include <string>\nint main() { std::string s("Happy 1024 from XOS C++!"); std::puts(s.c_str()); return 0; }\n',
    }
    (image_dir/'examples').mkdir(exist_ok=True)
    for name, body in examples.items():
        path = image_dir/'examples'/name; path.write_text('/* SPDX-License-Identifier: Apache-2.0 */\n'+body)
        transfer('import','/src/'+name,path)
    shutil.copyfile(out/'xos.img',image_dir/'xos.img')
    shutil.copyfile(ROOT/'scripts/release_launcher.py',image_dir/'launch.py')
    shutil.copytree(out/'sdk', sdk_dir, dirs_exist_ok=True)
    target = ROOT/'.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt'
    shutil.copytree(target/'include',sdk_dir/'cpp/include',dirs_exist_ok=True)
    (sdk_dir/'cpp/lib').mkdir(parents=True,exist_ok=True)
    for name in ('libstdc++.a','libsupc++.a','libgcc.a'):
        shutil.copyfile(target/'lib'/name,sdk_dir/'cpp/lib'/name)
    shutil.copyfile(target/'manifest.json',sdk_dir/'target_runtime_provenance.json')
    shutil.copytree(image_dir/'examples',sdk_dir/'examples',dirs_exist_ok=True)
    (sdk_dir/'compile.py').write_text(COMPILE_SCRIPT)
    notes = ROOT/'docs/releases'/('0.0.1-1024.md')
    for folder in (image_dir,sdk_dir):
        copy_notices(folder)
        shutil.copyfile(notes,folder/'README.md')
    release = {'name':'XylophoneOS Revival version '+VERSION,'version':VERSION,
               'system_build_id':system['build_id'],'xos_sha256':sha(out/'xos.img'),
               'seed_manifest_sha256':sha(ROOT/'build/cpp_bundle/seed_manifest.json'),
               'sysroot_manifest_sha256':sha(ROOT/'build/cpp_bundle/sysroot_manifest.json'),
               'stress_status':'separate agent running; not claimed passed',
               'guest_files':{item['guest_path']:item['sha256'] for item in entries},
               'notice':'static AMD64 BIOS/QEMU configuration; original licenses retained'}
    for folder in (image_dir,sdk_dir):
        (folder/'release.json').write_text(json.dumps(release,indent=2)+'\n')
    (out/'release_manifest.json').write_text(json.dumps(release,indent=2)+'\n')
    archive(image_dir,out/(PREFIX+'_images.tar.gz'))
    archive(sdk_dir,out/(PREFIX+'_sdk.tar.gz'))


COMPILE_SCRIPT = '''# SPDX-License-Identifier: Apache-2.0
"""Compile a static XOS application with an installed x86_64-elf cross compiler."""
import argparse, os, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('sources',nargs='+')
p.add_argument('-o','--output',required=True)
p.add_argument('--c',action='store_true',help='compile C instead of C++')
a=p.parse_args(); root=Path(__file__).resolve().parent
compiler=os.environ.get('XOS_CC' if a.c else 'XOS_CXX','x86_64-elf-gcc' if a.c else 'x86_64-elf-g++')
cmd=[compiler,'-mno-red-zone','-fno-pie','-fno-pic','-fno-stack-protector','-ftls-model=local-exec']
if not a.c:
 cmd+=['-std=gnu++17','-nostdinc++','-fuse-cxa-atexit']
 for name in ('','/x86_64-unknown-elf','/backward'):
  cmd+=['-isystem',str(root/'cpp/include/c++/16.2.0')+name]
cmd+=['-idirafter',str(root/'include'),'-nostdlib','-static','-no-pie','-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096','-T',str(root/'user.ld'),str(root/'crt0_posix.o'),*a.sources,'-Wl,--start-group']
cmd += [str(root/'lib/libxos.a'),str(root/'lib/libxos_loader.a')]
if not a.c:cmd += [str(root/'cpp/lib/libstdc++.a'),str(root/'cpp/lib/libsupc++.a')]
cmd += [str(root/'lib/libc.a'),str(root/'lib/libm.a'),str(root/'cpp/lib/libgcc.a'),'-Wl,--end-group','-o',a.output]
raise SystemExit(subprocess.run(cmd).returncode)
'''

if __name__ == '__main__':
    main()
