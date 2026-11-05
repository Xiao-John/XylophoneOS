# SPDX-License-Identifier: Apache-2.0
"""Qualify the actual release ISO, empty-dash work disk, SDK and installed tools."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from xypm_image import Disk
from xypm_format import require,sha_file
from release_launcher import build_command
from sdk_receipt import verify_sdk, verify_packaged_sdk, verify_copied_inputs

def check_sdk_devkit(sdk, metadata, binding, report):
    """The packaged SDK must run its own XYPm host backend without a source checkout."""
    tools = sdk / 'tools'
    for name in ('xos_app.py', 'xypm_format.py', 'xypm.py', 'xypm_image.py', 'adopt_sdk.py'):
        require((tools / name).is_file(), 'SDK devkit tool missing: ' + name)
    for name in ('scripts/xypm_disk_host.cpp', 'src/user/services/fatfs_unicode.cpp',
                 'src/third_party/fatfs/ff.c', 'src/third_party/fatfs/ff.h',
                 'src/third_party/fatfs/ffconf.h', 'src/third_party/fatfs/ff_string.h',
                 'src/third_party/fatfs/diskio.h'):
        require((sdk / name).is_file(), 'SDK xypm host source missing: ' + name)
    probe = ('import xos_app, xypm, xypm_format, xypm_image; '
             'print(xypm_image.host_tool())')
    output = subprocess.check_output([sys.executable, '-c', probe], cwd=tools, text=True).strip()
    require(Path(output).is_file(), 'SDK xypm host tool was not produced')
    require(not Path(output).resolve().is_relative_to(sdk.resolve()),
            'SDK xypm host cache was written inside the SDK tree')
    after = verify_packaged_sdk(sdk, metadata)
    require(after['tree_sha256'] == binding['tree_sha256'],
            'SDK tree changed after xypm host backend build')
    report['checks'].append('sdk_devkit_tools_and_xypm_host_backend')


def check_xypm_install(sdk, images, folder, report):
    """Install/query/remove a tiny package using only the packaged SDK tools."""
    tool = sdk / 'tools/xypm.py'
    profile_path = sdk / 'config/package/xos_x86_64_static_single_b2_v1.json'
    profile = json.loads(profile_path.read_text())
    package_id = 'blind.probe'
    root = folder / 'xypm_probe_root'
    files = []

    def add(relative, data, role='data'):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        files.append({'path': relative, 'type': 'file', 'size': path.stat().st_size,
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'role': role})

    license_path = 'usr/share/licenses/' + package_id + '/LICENSE'
    receipt_path = 'usr/share/' + package_id + '/build_receipt.json'
    add('usr/share/' + package_id + '/payload.txt', 'xypm release smoke\n')
    add(license_path, 'Apache-2.0 release-smoke fixture\n')
    receipt = {'app': package_id, 'status': 'release_smoke_fixture'}
    add(receipt_path, json.dumps(receipt, sort_keys=True) + '\n')
    manifest = {
        'format_version': 1, 'id': package_id, 'upstream_version': '0.0.1', 'revision': 0,
        'target_profile': profile['id'], 'required_features': [], 'runtime_dependencies': [],
        'licenses': [license_path], 'files': sorted(files, key=lambda item: item['path']),
        'build_receipt': {'path': receipt_path,
                          'sha256': hashlib.sha256((root / receipt_path).read_bytes()).hexdigest()},
        'source': 'release_smoke.py',
    }
    manifest_path = folder / 'xypm_probe_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    package = folder / 'xypm_probe.xpk'
    subprocess.run([sys.executable, str(tool), 'pack', '--profile', str(profile_path),
                    '--root', str(root), '--manifest', str(manifest_path), '-o', str(package)],
                   check=True, stdout=subprocess.DEVNULL)
    image = folder / 'xypm_probe.img'
    subprocess.run(['cp', '-c', str(images / 'work_disk.img'), str(image)], check=True)
    installed = folder / 'xypm_probe_installed.img'
    subprocess.run([sys.executable, str(tool), 'install', '--profile', str(profile_path),
                    '--image', str(image), '--output-image', str(installed), '--offline', str(package)],
                   check=True, stdout=subprocess.DEVNULL)
    query = json.loads(subprocess.check_output(
        [sys.executable, str(tool), 'list', '--profile', str(profile_path), '--image', str(installed)],
        text=True))
    require(any(item['id'] == package_id for item in query['packages']), 'xypm install query missed probe')
    removed = folder / 'xypm_probe_removed.img'
    subprocess.run([sys.executable, str(tool), 'remove', '--profile', str(profile_path),
                    '--image', str(installed), '--output-image', str(removed), '--offline', package_id],
                   check=True, stdout=subprocess.DEVNULL)
    query = json.loads(subprocess.check_output(
        [sys.executable, str(tool), 'list', '--profile', str(profile_path), '--image', str(removed)],
        text=True))
    require(not any(item['id'] == package_id for item in query['packages']), 'xypm remove left probe')
    report['checks'].append('sdk_xypm_install_query_remove')

def main():
    version=(ROOT/'VERSION').read_text().strip();release=ROOT/'build/releases'/version
    images=release/('xylophoneos_revival_'+version+'_images');sdk=release/('xylophoneos_revival_'+version+'_sdk')
    metadata=json.loads((release/'release_manifest.json').read_text())
    system=json.loads((release/'system_manifest.json').read_text())
    input_binding=verify_sdk(release/'sdk',system)
    require(input_binding==metadata['sdk_binding']['input'],'release SDK input differs from qualification')
    sdk_binding=verify_packaged_sdk(sdk,metadata)
    verify_copied_inputs(sdk,input_binding,metadata['sdk_binding']['runtime'])
    report={'status':'failed','version':version,'build_id':metadata['system_build_id'],'checks':[],'sdk_input':input_binding,'sdk_packaged_tree_sha256':sdk_binding['tree_sha256']}
    guest=None
    try:
        check_sdk_devkit(sdk,metadata,sdk_binding,report)
        with tempfile.TemporaryDirectory(prefix='xos_release_') as folder:
            folder=Path(folder);disk=folder/'work.img'
            check_xypm_install(sdk,images,folder,report)
            subprocess.run(['cp','-c',str(images/'work_disk.img'),str(disk)],check=True)
            with Disk(disk,folder,True) as backend:require(backend.info('/usr/bin/dash') is None,'dash preinstalled on release work disk')
            report['checks'].append('fresh_work_disk_has_no_dash')
            iso=images/'xos-install-dash.iso'
            launch=build_command('qemu-system-x86_64',iso,disk,None)
            require('order=d' in launch and any('media=cdrom' in x for x in launch),'launcher does not use ISO')
            report['checks'].append('launcher_defaults_to_install_iso')
            for kind in ('c','cpp'):
                binary=release/('sdk_'+kind+'.elf')
                subprocess.run([sys.executable,str(sdk/'compile.py'),*(['--c'] if kind=='c' else []),
                                str(images/'examples'/('hello.'+kind)),'-o',str(binary)],check=True)
                with Disk(disk,folder) as backend:backend.command('import','/out/sdk_'+kind+'.elf',binary)
            fixtures={
                'c_stage.sh':'''set -e
value=$(printf 'one\\ntwo\\n' | cat)
test "$value" = "one
two"
cat <<'EOF' > /out/heredoc.txt
ISO_C3_HEREDOC
EOF
(exec /usr/bin/cat /out/heredoc.txt)
echo RELEASE_DASH_C3_OK
''',
                'py3.py':'''import threading,json,zlib,gzip,zipfile,io,idna
seen=[]
t=threading.Thread(target=lambda: seen.append(42));t.start();t.join()
assert seen==[42]
assert json.loads(json.dumps({'x':42}))['x']==42
assert gzip.decompress(gzip.compress(b'XOS'))==b'XOS'
buf=io.BytesIO()
stamp=(2024,1,1,0,0,0)
with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
    z.writestr(zipfile.ZipInfo('x',stamp),'payload')
with zipfile.ZipFile(buf) as z:assert z.read('x')==b'payload'
assert idna.decode(idna.encode('例子.测试'))=='例子.测试'
print('RELEASE_PY3_THREADS_JSON_ZLIB_IDNA_OK')
''',
                'project.mk':'all:\n\tx86_64-elf-gcc -static --sysroot=/sysroot /src/hello.c -o /out/make_hello.elf\n\t/out/make_hello.elf\n'}
            with Disk(disk,folder) as backend:
                for name,body in fixtures.items():
                    path=folder/name;path.write_text(body);backend.command('import','/out/'+name,path)
            guest=Guest(iso,'release_package',work_disk=disk,iso=True)
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
            baseline=resources(guest);report['baseline']=baseline
            for kind,compiler in [('c','gcc'),('cpp','g++')]:
                expected=b'Hello from XOS C'+(b'++!' if kind=='cpp' else b'!')
                command(guest,'exec-driver /usr/bin/x86_64-elf-'+compiler+' -static --sysroot=/sysroot /src/hello.'+kind+' -o /out/hello_'+kind+'.elf',b'kind=exited code=0',timeout=180)
                command(guest,'exec-file /out/hello_'+kind+'.elf',expected,timeout=45)
                command(guest,'exec-file /out/sdk_'+kind+'.elf',expected,timeout=45)
                require(resources(guest)==baseline,'resource drift after compilers')
                report['checks']+=['packaged_native_'+kind,'packaged_sdk_'+kind]
            for name,line,expected in [('dash_c3','dash /out/c_stage.sh',b'RELEASE_DASH_C3_OK'),
                ('make','make -B -f /out/project.mk all',b'Hello from XOS C!'),
                ('python_py3','python3 /out/py3.py',b'RELEASE_PY3_THREADS_JSON_ZLIB_IDNA_OK'),
                ('xypm_query','xypm info python_idna',b'id: python_idna')]:
                command(guest,line,expected,timeout=180);require(resources(guest)==baseline,'resource drift: '+name);report['checks'].append(name)
            command(guest,'sync',b'[files] sync=ok',timeout=30)
            guest.close();(release/'package_serial.log').write_bytes(guest.output);guest=None
            with Disk(disk,folder,True) as backend:
                require(sha_file(backend.export('/usr/bin/dash'))==metadata['dash_sha256'],'ISO-installed dash differs from payload')
            report['checks'].append('iso_installed_dash_full_hash')
            report['status']='passed';report['final_resources']=baseline
    except Exception as e:
        report['error']=str(e)
        if guest:report['output_tail']=bytes(guest.output[-5000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(release/'package_failed_serial.log').write_bytes(guest.output)
        (release/'package_smoke_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
