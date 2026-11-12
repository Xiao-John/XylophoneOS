# SPDX-License-Identifier: Apache-2.0
"""Package the frozen, accepted XOS image/SDK and a new offline development disk."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from sdk_receipt import verify_sdk, verify_runtime, tree_receipt, verify_copied_inputs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
VERSION = (ROOT/'VERSION').read_text().strip()
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
    for component in json.loads((ROOT/'licenses/components.json').read_text())['components']:
        for notice in component.get('notices',[]):
            source=ROOT/notice
            target=destination/'third_party_notices'/notice
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)


def archive(source, output):
    with tarfile.open(output, 'w:gz', compresslevel=1) as tar:
        tar.add(source, arcname=source.name)
    print(output, output.stat().st_size, flush=True)


def prepare_daily_package(package, profile_path, sdk, system, entries, wheel_package):
    """Preflight the candidate package against the actual release inputs."""
    from xos_app import tree_receipt as sdk_tree_receipt
    from xypm_format import load_json, require, strict_json, verify_package
    require(not wheel_package, 'daily and wheel packages use distinct profiles; migrate them before combining')
    profile = load_json(profile_path)
    require(system['build_id'] in profile.get('verified_system_builds', []), 'daily profile does not admit release system')
    digest, _ = sdk_tree_receipt(sdk)
    require(digest in profile.get('sdk_tree_sha256', []), 'daily profile does not admit release SDK')
    receipt_data = bytearray()
    receipt_path = 'usr/share/xos.daily_utilities/build_receipt.json'
    def sink(event, item, data):
        if item['path'] == receipt_path and event == 'data':
            require(len(receipt_data) + len(data) <= 1048576, 'daily build receipt too large')
            receipt_data.extend(data)
    package_info = verify_package(package, profile, sink=sink)
    manifest = package_info['manifest']
    require(manifest['id'] == 'xos.daily_utilities', 'not a daily utility package')
    require(manifest['build_receipt']['path'] == receipt_path, 'unexpected daily build receipt path')
    receipt = strict_json(bytes(receipt_data))
    require(receipt['sdk_tree_sha256'] == digest, 'daily ELF build SDK differs from release SDK')
    existing = {item['guest_path'].lower() for item in entries}
    for item in manifest['files']:
        require(('/' + item['path']).lower() not in existing, 'daily package conflicts with release input: ' + item['path'])
    return profile, package_info


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release-dir', type=Path, default=ROOT/'build/releases'/VERSION)
    p.add_argument('--dash-manifest',type=Path,required=True)
    p.add_argument('--cpython-stage',type=Path)
    p.add_argument('--extra-elf',action='append',default=[],metavar='NAME=PATH')
    p.add_argument('--wheel-package',type=Path)
    p.add_argument('--daily-package', type=Path, help='explicit daily utilities candidate XPK')
    p.add_argument('--daily-profile', type=Path, help='profile bound to the daily package and release SDK')
    p.add_argument('--daily-sdk', type=Path, help='composed SDK used by daily utilities; must match system SDK and C++ runtime')
    a = p.parse_args()
    if bool(a.daily_package) != bool(a.daily_profile):
        p.error('--daily-package and --daily-profile must be supplied together')
    if a.daily_sdk and not a.daily_package:
        p.error('--daily-sdk requires --daily-package and --daily-profile')
    out = a.release_dir.resolve(strict=True)
    if ROOT/'build/releases' not in out.parents:
        p.error('use a dedicated build/releases directory')
    system = json.loads((out/'system_manifest.json').read_text())
    if sha(out/'xos-install.iso') != system['artifacts']['xos-install.iso']['sha256']:
        p.error('frozen install ISO differs from accepted manifest')
    sdk_input = verify_sdk(out/'sdk', system)
    target = ROOT/'.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt'
    runtime_input = verify_runtime(target, json.loads((ROOT/'config/release_cpp_runtime_v5.json').read_text()))
    seed = json.loads((ROOT/'build/cpp_bundle/seed_manifest.json').read_text())
    sysroot = json.loads((ROOT/'build/cpp_bundle/sysroot_manifest.json').read_text())
    from seed_preflight import validate_bundle
    result = validate_bundle(seed, ROOT, sysroot, ROOT, required_tools=('gcc','cc1','g++','cc1plus','as','ld','ar','ranlib'))
    if not result.ok:
        raise ValueError(result.diagnostics)
    image_dir, sdk_dir = out/(PREFIX+'_images'), out/(PREFIX+'_sdk')
    if image_dir.exists() or sdk_dir.exists():
        p.error('refuse existing image/SDK staging directories; choose a fresh release directory')
    disk = image_dir/'work_disk.img'
    if disk.exists():
        p.error('refuse to overwrite release work disk')
    helper = ROOT/'build/work_disk_host'
    if not helper.is_file():
        p.error('build/work_disk_host must already be prepared; do not rebuild shared tools')
    entries = list(seed['install_files']) + list(sysroot['files'])
    diagnostic = out / 'user_xos_diag.image.elf'
    diagnostic_hash = system['artifacts']['user_xos_diag.image.elf']['sha256']
    if sha(diagnostic) != diagnostic_hash:
        p.error('frozen xos-diag differs from system manifest')
    entries.append({'path': str(diagnostic), 'guest_path': '/usr/bin/xos-diag',
                    'sha256': diagnostic_hash})
    if a.cpython_stage:
        stage_manifest=json.loads(a.cpython_stage.read_text())
        # Stage directory name mirrors the manifest stem (stage_py3 / stage_py3_b).
        stage_root=a.cpython_stage.parent/a.cpython_stage.stem.replace('_manifest','')
        for item in stage_manifest['files']:
            source=stage_root/item['path'].lstrip('/')
            if sha(source)!=item['sha256']:raise ValueError('CPython stage changed: '+item['path'])
            entries.append({'path':str(source.resolve()),'guest_path':item['path'],'sha256':item['sha256']})
    for item in a.extra_elf:
        name,source=item.split('=',1)
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in name):raise ValueError('invalid program name')
        source=Path(source).resolve(strict=True)
        entries.append({'path':str(source),'guest_path':'/usr/bin/'+name,'sha256':sha(source)})
    if len({e['guest_path'].lower() for e in entries})!=len(entries):raise ValueError('duplicate guest path')
    if a.daily_sdk:
        verify_copied_inputs(a.daily_sdk, sdk_input, runtime_input)
    daily_sdk = a.daily_sdk if a.daily_sdk else out/'sdk'
    daily = (prepare_daily_package(a.daily_package, a.daily_profile, daily_sdk, system, entries, a.wheel_package)
             if a.daily_package else None)
    image_dir.mkdir()
    sdk_dir.mkdir()
    from make_work_disk import create_fat32
    create_fat32(disk, 2048)
    directories = {'/bin','/src','/out','/tmp'}
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
    # dash is carried by the ISO only; fresh release work disks must not contain it.
    dash=json.loads(a.dash_manifest.read_text())
    dash_elf=ROOT/dash['elf']
    if sha(dash_elf)!=dash['sha256']:raise ValueError('dash manifest mismatch')
    install=json.loads((out/'install_manifest.json').read_text())
    if install['dash_sha256']!=dash['sha256'] or install['build_id']!=system['build_id']:
        raise ValueError('install ISO is not bound to the frozen system/dash')
    if a.wheel_package:
        from xypm_image import transact
        from xypm_format import load_json,DEFAULT_PROFILE
        candidate=image_dir/'wheel_candidate.img'
        profile=load_json(ROOT/'config/package/xos_x86_64_static_single_b2_v1.json')
        receipt=transact(disk,candidate,profile,'install',package=a.wheel_package)
        candidate.replace(disk)
        (out/'wheel_install_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if daily:
        from xypm_image import transact
        profile, package_info = daily
        candidate = image_dir/'daily_candidate.img'
        receipt = transact(disk, candidate, profile, 'install', package=a.daily_package,
                           expected_sha256=package_info['sha256'])
        candidate.replace(disk)
        (out/'daily_install_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    examples = {
        'hello.c': '#include <stdio.h>\nint main(void) { puts("Hello from XOS C!"); return 0; }\n',
        'hello.cpp': '#include <cstdio>\n#include <string>\nint main() { std::string s("Hello from XOS C++!"); std::puts(s.c_str()); return 0; }\n',
    }
    (image_dir/'examples').mkdir(exist_ok=True)
    for name, body in examples.items():
        path = image_dir/'examples'/name; path.write_text('/* SPDX-License-Identifier: Apache-2.0 */\n'+body)
        transfer('import','/src/'+name,path)
    # xos-install.iso is the only regular boot product; legacy floppy/embedded images are gone.
    shutil.copyfile(out/'xos-install.iso',image_dir/'xos-install.iso')
    shutil.copyfile(out/'xos-install-dash.iso',image_dir/'xos-install-dash.iso')
    shutil.copyfile(out/'install_manifest.json',image_dir/'install_manifest.json')
    shutil.copyfile(ROOT/'scripts/release_launcher.py',image_dir/'launch.py')
    shutil.copytree(out/'sdk', sdk_dir, dirs_exist_ok=True)
    shutil.copytree(target/'include',sdk_dir/'cpp/include',dirs_exist_ok=True)
    (sdk_dir/'cpp/lib').mkdir(parents=True,exist_ok=True)
    for name in ('libstdc++.a','libsupc++.a','libgcc.a'):
        shutil.copyfile(target/'lib'/name,sdk_dir/'cpp/lib'/name)
    shutil.copyfile(target/'manifest.json',sdk_dir/'target_runtime_provenance.json')
    shutil.copytree(image_dir/'examples',sdk_dir/'examples',dirs_exist_ok=True)
    (sdk_dir/'compile.py').write_text(COMPILE_SCRIPT)
    notes = ROOT/'docs/releases'/(VERSION+'.md')
    for folder in (image_dir,sdk_dir):
        copy_notices(folder)
        shutil.copyfile(notes,folder/'README.md')
    stage_dev_kit(sdk_dir)
    if verify_sdk(out/'sdk',system) != sdk_input:
        raise ValueError('SDK changed while packaging')
    if verify_runtime(target,json.loads((ROOT/'config/release_cpp_runtime_v5.json').read_text())) != runtime_input:
        raise ValueError('runtime changed while packaging')
    if daily:
        if a.daily_sdk:
            verify_copied_inputs(a.daily_sdk, sdk_input, runtime_input)
        checked = prepare_daily_package(a.daily_package, a.daily_profile, daily_sdk, system, entries, a.wheel_package)
        if checked[1]['sha256'] != daily[1]['sha256']:
            raise ValueError('daily package changed while packaging')
    verify_copied_inputs(sdk_dir,sdk_input,runtime_input)
    sdk_binding={'input':sdk_input,'runtime':runtime_input,
                 'packaged':tree_receipt(sdk_dir,exclude=('release.json',))}
    release = {'name':'XylophoneOS Revival version '+VERSION,'version':VERSION,
               'system_build_id':system['build_id'],'sdk_binding':sdk_binding,'xos_sha256':sha(out/'xos-install.iso'),
               'seed_manifest_sha256':sha(ROOT/'build/cpp_bundle/seed_manifest.json'),
               'sysroot_manifest_sha256':sha(ROOT/'build/cpp_bundle/sysroot_manifest.json'),
               'install_iso_sha256':sha(out/'xos-install-dash.iso'),
               'dash_sha256':dash['sha256'],'dash_installation':'ISO payload; absent on fresh work disk',
               'stress_status':'not_rerun',
               'guest_files':{item['guest_path']:item['sha256'] for item in entries},
               'notice':'static AMD64 BIOS/QEMU configuration; original licenses retained'}
    if daily:
        profile, package_info = daily
        release['daily_package'] = {'sha256': package_info['sha256'], 'profile': profile['id'],
                                    'scope': profile.get('scope', 'unspecified')}
        for item in package_info['manifest']['files']:
            release['guest_files']['/' + item['path']] = item['sha256']
    for folder in (image_dir,sdk_dir):
        (folder/'release.json').write_text(json.dumps(release,indent=2)+'\n')
    (out/'release_manifest.json').write_text(json.dumps(release,indent=2)+'\n')
    archive(image_dir,out/(PREFIX+'_images.tar.gz'))
    archive(sdk_dir,out/(PREFIX+'_sdk.tar.gz'))



def stage_dev_kit(sdk_dir):
    """Attach host-side docs, XPK tools, profiles and a sample project to the packaged SDK."""
    import shutil
    docs = sdk_dir / 'docs'
    (docs / 'usage').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'docs/usage/index.md', docs / 'usage/index.md')
    userland = ROOT / 'docs/usage/userland'
    if userland.is_dir():
        shutil.copytree(userland, docs / 'usage/userland', dirs_exist_ok=True)
    (docs / 'releases').mkdir(parents=True, exist_ok=True)
    for name in ('playbook.md', 'SDK_DEVELOPING.md'):
        src = ROOT / 'docs/releases' / name
        if src.is_file():
            shutil.copyfile(src, docs / 'releases' / name)
    shutil.copyfile(ROOT / 'docs/releases/SDK_DEVELOPING.md', sdk_dir / 'DEVELOPING.md')
    tools = sdk_dir / 'tools'
    tools.mkdir(exist_ok=True)
    for name in ('xos_app.py', 'xypm_format.py', 'xypm.py', 'xypm_image.py'):
        shutil.copyfile(ROOT / 'scripts' / name, tools / name)
    shutil.copyfile(ROOT / 'scripts/sdk_adopt_profile.py', tools / 'adopt_sdk.py')
    # xypm_image compiles its private FatFs host backend on first use.  Keep the
    # relative source layout it expects inside the SDK so offline install works
    # without the XOS source checkout.
    host_sources = [
        ROOT / 'scripts/xypm_disk_host.cpp',
        ROOT / 'src/user/services/fatfs_unicode.cpp',
        ROOT / 'src/third_party/fatfs/ff.c',
        *sorted((ROOT / 'src/third_party/fatfs').glob('*.h')),
    ]
    for source in host_sources:
        destination = sdk_dir / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    cfg = sdk_dir / 'config' / 'package'
    cfg.mkdir(parents=True, exist_ok=True)
    for src in sorted((ROOT / 'config/package').glob('*.json')):
        shutil.copyfile(src, cfg / src.name)
    sample = sdk_dir / 'examples' / 'xpk_hello'
    (sample / 'src').mkdir(parents=True, exist_ok=True)
    (sample / 'src' / 'main.cpp').write_text(
        '// SPDX-License-Identifier: Apache-2.0\n'
        '#include <cstdio>\n#include <string>\n'
        'int main() { std::puts("Hello from XOS package: xos.hello"); return 0; }\n')
    shutil.copyfile(sdk_dir / 'LICENSE', sample / 'LICENSE')
    app = {
        'format_version': 1, 'id': 'xos.hello', 'upstream_version': '0.1.0', 'revision': 0,
        'target_profile': 'xos-x86_64-sdk-local', 'language': 'cpp',
        'sources': ['src/main.cpp'],
        'required_features': ['stdio', 'cxx_runtime'],
        'runtime_dependencies': [],
        'files': [
            {'source': 'build/hello.elf', 'path': 'usr/bin/hello', 'role': 'executable'},
            {'source': 'LICENSE', 'path': 'usr/share/licenses/xos.hello/LICENSE', 'role': 'data'},
            {'source': 'src/main.cpp', 'path': 'usr/share/xos.hello/source/main.cpp', 'role': 'data'},
        ],
        'licenses': ['usr/share/licenses/xos.hello/LICENSE'],
    }
    import hashlib as _hashlib
    (sample / 'xos_app.json').write_text(
        json.dumps(app, indent=2, ensure_ascii=False, sort_keys=True) + '\n')
    (sample / '.gitignore').write_text('build/\ndist/\n')


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
