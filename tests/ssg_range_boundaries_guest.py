#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run live QtScene range boundary checks in the XOS guest."""
import argparse, hashlib, json, re, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from ssg_public_paths import portable, resolve_template
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer
p=argparse.ArgumentParser()
for name in ('image','payload','output'): p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
receipt=json.loads(a.payload.with_suffix('.receipt.json').read_text())
assert sha(a.payload)==receipt['elf_sha256']
for name,digest in receipt['inputs'].items(): assert sha(resolve_template(name,[('XOS_ARTIFACT_DIR',a.payload.resolve().parent)]))==digest,name
report={'status':'FAILED','image_sha256':sha(a.image),'payload_sha256':sha(a.payload),'checks':[]};g=None;disk=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_range_boundaries_') as td:
  disk=Path(td)/'work.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/probe.elf',a.payload)
  g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=45)
  command(g,'demo quiet',b'demo tasks stopped');command(g,'display-start',b'result=0');g.expect(b'[display-service] ready');report['resources_before']=resources(g)
  start=len(g.output);send_bytes(g,b'exec-driver /bin/probe.elf\r');g.expect(b'SSG_RANGE_TEST_DONE',start=start,timeout=120);g.expect_supervisor(start=start,timeout=60)
  output=bytes(g.output)[start:];report['checks']=[{'name':n.decode(),'status':s.decode()} for n,s in re.findall(rb'SSG_RANGE_CHECK ([a-z_]+)=(PASS|FAIL)',output)]
  report['resources_after']=resources(g)
  if len(report['checks'])==13 and all(c['status']=='PASS' for c in report['checks']) and report['resources_before']==report['resources_after'] and b'SSG_RANGE_TEST_DONE checks=13 failures=0' in output and b'kind=exited code=0' in output: report['status']='PASSED'
finally:
 if g: (out/'serial.log').write_bytes(bytes(g.output));g.close()
 report['qemu_command_kind']='template; the runner creates the work disk and QMP socket'
 mappings=[('XOS_IMAGE',a.image),('XOS_TEST_OUT',out),('XOS_RANGE_TEST_ELF',a.payload),('XOS_WORK_DISK',disk),('XOS_QMP_SOCKET',g.qmp_path if g else None),('XOS_QEMU',g.command[0] if g else None)]
 (out/'report.json').write_text(json.dumps(portable(report,mappings,strict=True),indent=2)+'\n')
print(report['status'],len(report['checks']),'checks')
sys.exit(0 if report['status']=='PASSED' else 1)
