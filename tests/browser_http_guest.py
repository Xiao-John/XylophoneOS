# SPDX-License-Identifier: Apache-2.0
"""Cross-build and run parser vectors in an actual XOS process; no network claim."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'scripts')]
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from process_smoke import command, resources
from make_work_disk import create_fat32
from work_disk import transfer

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    name = str(out.relative_to(ROOT/'build'))+'/guest'
    wrapper = out/'parser_probe.cpp'
    wrapper.write_text('#include "'+str(ROOT/'src/ports/browser_http/http.cpp')+'"\n'+
                       '#include "'+str(ROOT/'tests/browser_http/probe.cpp')+'"\n')
    elf = out/'parser.elf'
    cmd = [sys.executable,str(args.sdk.resolve()/'compile.py'),str(wrapper),'-o',str(elf)]
    built = subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (out/'build.log').write_text(built.stdout)
    if built.returncode:
        raise SystemExit(built.stdout)
    paths = [ROOT/'src/ports/browser_http/http.hpp',ROOT/'src/ports/browser_http/http.cpp',
             ROOT/'tests/browser_http/probe.cpp',args.sdk/'manifest.json',args.image,elf]
    report = {'status':'FAILED','evidence_kind':'XOS_guest_parser_only','network':'NOT_RUN',
              'build_command':cmd,'input_sha256':{str(s.resolve()):digest(s) for s in paths},'runs':[]}
    g = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_http_parser_') as temp:
            disk = Path(temp)/'work.img'
            create_fat32(disk,512)
            transfer(disk,'mkdir','/bin')
            transfer(disk,'import','/bin/parser.elf',elf)
            g=Guest(args.image.resolve(),name,work_disk=disk)
            report['qemu_command']=g.command
            g.expect(b'xos64> ',timeout=40)
            send_bytes(g,b'run\r')
            g.expect_supervisor(trace=True)
            pump(g,1.5)
            baseline=resources(g)
            report['baseline_resources']=baseline
            for iteration in range(3):
                result=command(g,'exec-file /bin/parser.elf',b'kind=exited code=0',timeout=60)
                assert b'malformed_vectors=4096 result=PASSED' in result,result[-2000:]
                after=resources(g)
                assert after==baseline,(baseline,after)
                report['runs'].append({'iteration':iteration,'status':'PASSED','resources_after':after})
            report['status']='PASSED'
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        if g:
            (out/'serial.log').write_bytes(g.output)
            g.close()
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASSED: three actual XOS parser process runs and exact resource return; network NOT_RUN')

if __name__=='__main__':
    main()
