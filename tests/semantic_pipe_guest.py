#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a bounded delegated parent/child pipe probe in xsh and dash."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'scripts')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer

parser = argparse.ArgumentParser()
for name in ('image','payload','dash','output'):
    parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args()
out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={'status':'FAILED','image_sha256':sha(args.image),'payload_sha256':sha(args.payload),
        'dash_sha256':sha(args.dash),'checks':[]}
guest=None
try:
    with tempfile.TemporaryDirectory(prefix='xos_semantic_pipe_') as tmp:
        tmp=Path(tmp);disk=tmp/'work.img';create_fat32(disk,512)
        transfer(disk,'mkdir','/bin')
        transfer(disk,'import','/bin/semantic-pipe.elf',args.payload)
        transfer(disk,'import','/bin/dash',args.dash)
        script=tmp/'dash-pipe.sh';script.write_text('/bin/semantic-pipe.elf\necho PIPE_DASH_STATUS:$?\n')
        transfer(disk,'import','/dash-pipe.sh',script)
        guest=Guest(args.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk)
        report['qemu_command']=guest.command
        guest.expect(b'xos64> ',timeout=45);send_bytes(guest,b'run\r')
        guest.expect_supervisor(trace=True,timeout=45)
        command(guest,'demo quiet',b'demo tasks stopped',timeout=20)
        baseline=resources(guest);report['baseline_resources']=baseline
        start=len(guest.output);send_bytes(guest,b'exec-driver /bin/semantic-pipe.elf\r')
        guest.expect(b'PIPE_PROBE_DONE failures=',start=start,timeout=60)
        guest.expect_supervisor(start=start,timeout=30)
        output=bytes(guest.output)[start:]
        report['checks']=[{'name':n.decode(),'status':s.decode()}
                          for n,s in re.findall(rb'PIPE_PROBE ([a-z_]+)=(PASS|FAIL)',output)]
        assert len(report['checks'])==12 and all(c['status']=='PASS' for c in report['checks'])
        assert b'kind=exited code=0' in output
        assert resources(guest)==baseline
        start=len(guest.output);send_bytes(guest,b'exec-driver /bin/dash /dash-pipe.sh\r')
        guest.expect(b'PIPE_PROBE child_start=FAIL error=-1',start=start,timeout=60)
        guest.expect(b'PIPE_DASH_STATUS:2',start=start,timeout=30)
        guest.expect_supervisor(start=start,timeout=30)
        report['dash']='EXPECTED_DENIAL: probe did not inherit child-spawn authority'
        report['after_resources']=resources(guest)
        assert report['after_resources']==baseline
        command(guest,'sync',b'[files] sync=ok')
        report['status']='PASSED_SCOPED_PROBE'
except Exception as error:
    report['error']=repr(error)
    raise
finally:
    if guest:guest.close()
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'],len(report['checks']),'xsh checks; dash denial observed')
