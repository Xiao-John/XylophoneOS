#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise file-service exit with a dedicated, explicitly fault-injected system."""
import argparse,hashlib,json,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from task_smoke import send_bytes,pump
from process_smoke import command
p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--injected-source',type=Path,required=True);a=p.parse_args()
out=ROOT/'build/fb0/service_exit';out.mkdir(parents=True,exist_ok=True)
hash_file=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
system_manifest=json.loads((a.image.parent/'manifest.json').read_text())
assert hash_file(a.image)==system_manifest['artifacts'][a.image.name]['sha256']
assert hash_file(a.injected_source)==system_manifest['sources']['src/user/services/files.cpp']
probe_report=json.loads((ROOT/'build/fb0/report.json').read_text())
assert probe_report['status']=='passed' and hash_file(a.probe)==probe_report['elf_sha256']
report={'status':'failed','image_sha256':hash_file(a.image),'probe_sha256':hash_file(a.probe),'injected_source_sha256':hash_file(a.injected_source),'injection':'test-only UD2 in file service on stat /FB0FAULT','build_id':system_manifest['build_id'],'baseline_build_id':probe_report['build_id'],'checks':[]};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_fb0_service_') as d:
  disk=Path(d)/'disk.img';create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/probe.elf',a.probe)
  g=Guest(a.image.resolve(),'fb0/service_exit/guest',work_disk=disk);report['qemu_command']=g.command
  g.expect(b'xos64> ',timeout=35);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=35)
  command(g,'demo keep',b'demo: keep')
  for pid in (1,3,4):command(g,f'kill {pid}',b'kill: accepted')
  pump(g,.5);result=command(g,'exec-file /bin/probe.elf service_exit',b'FB0_SERVICE_EXIT_PING=',timeout=90)
  match=re.search(rb'\[task\] event=fault pid=8 vector=6',result);assert match,result[-3000:]
  stat=re.search(rb'FB0_SERVICE_EXIT_STAT=(-?\d+)',result);ping=re.search(rb'FB0_SERVICE_EXIT_PING=(-?\d+)',result)
  assert stat and ping and int(stat.group(1))==-8 and int(ping.group(1))==-7 and b'kind=exited code=0' in result,result[-3000:]
  report['checks'].append({'name':'inflight_request_then_service_exit','stat':int(stat.group(1)),'ping':int(ping.group(1))})
  command(g,'stats',b'completions=');report['checks'].append({'name':'supervisor_remains_responsive'})
  report['status']='passed'
except Exception as error:report['error']=str(error);raise
finally:
 if g:(out/'serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS service exit:',report['checks'])
