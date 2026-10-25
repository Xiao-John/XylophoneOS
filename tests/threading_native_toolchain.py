# SPDX-License-Identifier: Apache-2.0
"""Run released, unmodified XOS-hosted GCC/G++ on a private candidate work disk."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes, pump
ARCHIVE_SHA='a800969aaed03c601b8eb5029da8df1f4faecc5fa7f66ede28482aa65c7be25a'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release-images',required=True,type=Path)
    args=p.parse_args()
    assert sha(args.release_images)==ARCHIVE_SHA,'release archive SHA256 mismatch/incomplete download'
    build=ROOT/'build'; version=json.loads((build/'manifest.json').read_text())['build_id']
    report={'status':'failed','build_id':version,'release_archive_sha256':ARCHIVE_SHA,'checks':[],'commands':[]}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_thread_native_') as folder:
            temp=Path(folder);disk=temp/'candidate.img';image=temp/'boot.img'
            with tarfile.open(args.release_images) as archive:
                members=[m for m in archive if m.isfile() and m.name.endswith('/work_disk.img')]
                assert len(members)==1
                with archive.extractfile(members[0]) as source,disk.open('wb') as output:
                    shutil.copyfileobj(source,output)
            shutil.copyfile(build/'xos.img',image)
            inputs={
                'thread_c.c':b'#include <stdio.h>\nint main(void){puts("[legacy] native GCC C=ok");return 0;}\n',
                'thread_cpp.cpp':b'#include <string>\n#include <cstdio>\nint main(){std::string s("[legacy] native G++ C++=ok");std::puts(s.c_str());return 0;}\n',
                'thread_bad.c':b'int main(void) { this is not C; }\n'}
            for name,data in inputs.items():
                path=temp/name;path.write_bytes(data);transfer(disk,'import','/src/'+name,path)
            guest=Guest(image,'threading_native',work_disk=disk)
            guest.expect(b'xos64> ',timeout=30);send_bytes(guest,b'run\r')
            guest.expect_supervisor(trace=True,timeout=30);pump(guest,1.5)
            baseline=resources(guest);report['resource_baseline']=baseline
            cases=[
                ('exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot /src/thread_c.c -o /out/thread_c.elf',0,None),
                ('exec-file /out/thread_c.elf',0,b'[legacy] native GCC C=ok'),
                ('exec-driver /usr/bin/x86_64-elf-g++ -static --sysroot=/sysroot /src/thread_cpp.cpp -o /out/thread_cpp.elf',0,None),
                ('exec-file /out/thread_cpp.elf',0,b'[legacy] native G++ C++=ok'),
                ('exec-driver /usr/bin/x86_64-elf-gcc -static --sysroot=/sysroot /src/thread_bad.c -o /out/thread_bad.elf',None,b'error:')]
            for line,expected,marker in cases:
                output=command(guest,line,b'kind=exited code=',timeout=240)
                match=re.search(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)',output)
                code=int(match[1]) if match else None
                assert code==expected if expected is not None else code is not None and code!=0,output[-5000:]
                if marker:assert marker in output,output[-5000:]
                after=resources(guest);assert after==baseline,(baseline,after)
                report['commands'].append({'line':line,'exit_code':code,'resources_after':after,'output':output.decode(errors='replace')})
            command(guest,'sync',b'[files] sync=ok');guest.close();guest=None
            for name,data in inputs.items():
                exported=temp/('saved_'+name);transfer(disk,'export','/src/'+name,exported)
                assert exported.read_bytes()==data
            assert sha(args.release_images)==ARCHIVE_SHA
            report['checks']=['real_released_GCC_compiles_inside_new_kernel','real_released_G++_compiles_inside_new_kernel',
                'both_guest_generated_ELFs_execute','compile_errors_stay_nonzero','process_resources_return_to_baseline',
                'source_bytes_persist_after_sync_and_source_release_archive_unchanged']
            report['status']='passed';print('PASS 6 native compiler regression groups | build',version)
    except Exception as error:report['error']=str(error);raise
    finally:
        if guest:guest.close()
        (build/'threading_native_report.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
