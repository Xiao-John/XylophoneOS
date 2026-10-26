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

def main():
    version=(ROOT/'VERSION').read_text().strip();release=ROOT/'build/releases'/version
    images=release/('xylophoneos_revival_'+version+'_images');sdk=release/('xylophoneos_revival_'+version+'_sdk')
    metadata=json.loads((release/'release_manifest.json').read_text())
    report={'status':'failed','version':version,'build_id':metadata['system_build_id'],'checks':[]}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_release_') as folder:
            folder=Path(folder);disk=folder/'work.img'
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
