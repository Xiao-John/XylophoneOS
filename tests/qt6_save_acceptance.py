#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""G05 save failures: actual FAT full/RDO, partial staging, boundary faults, kill."""
import argparse,hashlib,json,re,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
receipt=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==receipt['elf_sha256']
for n,h in receipt['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','image_sha256':sha(a.image),'elf_sha256':sha(a.payload),'checks':[],'scope':'real guest FAT full/read-only and killed process; close/sync/commit status errors are explicit consumer-boundary injections, not hardware disk-failure or power-loss qualification'};g=None

from qt6_fat_fixture import alter
def boot(disk,name):
 global g
 g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/'+name,work_disk=disk);g.expect(b'xos64> ',timeout=45);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);return resources(g)
def close(name):
 global g
 (out/(name+'.serial.log')).write_bytes(g.output);g.close();g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_save_failures_') as tmp:
  tmp=Path(tmp);fixture=tmp/'original';fixture.write_bytes(b'original UTF-8: caf\xc3\xa9\n')
  for mode in ('readonly','full','short','close','sync','commit-unknown','qsave','hold','badpath','missing'):
   disk=tmp/(mode+'.img');create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/save.elf',a.payload);transfer(disk,'import','/LOCK.TXT',fixture)
   if mode in ('readonly','full'):alter(disk,mode)
   before=boot(disk,mode)
   if mode=='hold':
    b=len(g.output);send_bytes(g,b'spawn-file /bin/save.elf hold /LOCK.TXT\r');g.expect(b'SAVE_HOLD_STAGED',start=b,timeout=90);pid=int(re.search(rb'\[loader\] started pid=(\d+)',bytes(g.output)[b:])[1]);command(g,f'kill {pid}',b'kill: accepted');command(g,f'wait {pid}',b'kind=killed');command(g,'cat /LOCK.TXT',b'original UTF-8:');command(g,'sync',b'[files] sync=ok')
   elif mode=='missing':
    result=command(g,'exec-file /bin/save.elf short /missing/path.txt',b'kind=exited code=3',timeout=90)
   else:
    result=command(g,'exec-file /bin/save.elf '+mode+' /LOCK.TXT',b'kind=exited code=0',timeout=90)
    marker=b'QSAVE_EXISTING_REPLACE_UNSUPPORTED_OLD_RETAINED' if mode=='qsave' else b'SAVE_COMMIT_ERROR_UNKNOWN_NEW_COMPLETE_NOT_FALSE_SUCCESS' if mode=='commit-unknown' else b'SAVE_FAILURE_OLD_BYTES_RETAINED'
    assert marker in result,result[-2000:]
    command(g,'sync',b'[files] sync=ok')
   assert resources(g)==before;cmd=g.command;close(mode)
   exported=tmp/(mode+'.bytes');transfer(disk,'export','/LOCK.TXT',exported)
   wanted=b'replacement\n' if mode=='commit-unknown' else fixture.read_bytes();assert exported.read_bytes()==wanted
   if mode=='hold':
    boot(disk,'hold-reboot');command(g,'cat /LOCK.TXT',b'original UTF-8:');close('hold-reboot');rebooted=tmp/'hold-reboot.bytes';transfer(disk,'export','/LOCK.TXT',rebooted);assert rebooted.read_bytes()==wanted
   report['checks'].append({'name':mode,'status':'PASSED','resources':before,'qemu_command':cmd,'bytes_sha256':sha(exported),'original_preserved':mode!='commit-unknown','outcome':'reported unknown, complete new bytes observed' if mode=='commit-unknown' else 'old bytes unchanged'})
   print(mode,'PASSED',flush=True)
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:close('failed')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
