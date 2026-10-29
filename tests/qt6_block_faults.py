#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual QEMU blkdebug write/flush errors through guest ATA and file service."""
import argparse,hashlib,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import command,resources
from make_work_disk import create_fat32
from work_disk import transfer
p=argparse.ArgumentParser()
for n in ('image','payload','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=json.loads(a.payload.with_suffix('.receipt.json').read_text());assert sha(a.payload)==r['elf_sha256']
for n,h in r['inputs'].items():assert sha(n)==h,n
report={'status':'FAILED','image_sha256':sha(a.image),'elf_sha256':sha(a.payload),'checks':[],'mechanism':'QEMU blkdebug EIO at host block write/flush; real guest ATA error propagation, not power loss or torn sectors'};g=None
try:
 with tempfile.TemporaryDirectory(prefix='xos_qt_block_fault_') as tmp:
  tmp=Path(tmp);original=tmp/'original';original.write_bytes(b'Old bytes must survive a storage error.\n')
  for event in ('flush_to_disk','write_aio'):
   disk=tmp/(event+'.img');create_fat32(disk,512);transfer(disk,'mkdir','/bin');transfer(disk,'import','/bin/save.elf',a.payload);transfer(disk,'import','/LOCK.TXT',original)
   base_command=boot_smoke.qemu_command
   def qemu(*args,**kw):
    cmd=base_command(*args,**kw)
    for i,v in enumerate(cmd):
     if v.startswith('file='+str(disk)+','):cmd[i]=v+',id=workdisk,node-name=workraw,werror=report,rerror=report'
    return cmd
   with patch.object(boot_smoke,'qemu_command',qemu):g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/'+event,work_disk=disk)
   g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);base=resources(g)
   begin=len(g.output);send_bytes(g,b'exec-file /bin/save.elf hold /LOCK.TXT\r');g.expect(b'SAVE_HOLD_STAGED',start=begin,timeout=90)
   # The payload is already loaded and actual bytes are staged. Freeze the VM,
   # splice a QEMU blkdebug filter into this disposable disk's block graph, and
   # resume before the real file-service precommit sync. No guest success stub.
   g.qmp('stop');nodes=g.qmp('query-named-block-nodes')
   file_node=next(n['node-name'] for n in nodes if n['drv']=='file' and n.get('file')==str(disk))
   g.qmp('blockdev-add',{'driver':'blkdebug','node-name':'savefault','image':file_node,'inject-error':[{'event':event,'errno':5,'once':True}]})
   g.qmp('blockdev-reopen',{'options':[{'driver':'raw','node-name':'workraw','file':'savefault'}]})
   g.qmp('cont');g.expect(b'kind=exited code=',start=begin,timeout=60);g.expect_supervisor(start=begin)
   result=bytes(g.output)[begin:]
   assert b'SAVE_RESULT saved=0 unknown=0' in result and (b'kind=exited code=0' in result or b'kind=exited code=6' in result),result[-3000:]
   assert resources(g)==base;sync_result=command(g,'sync',b'xsh> ');(out/(event+'.serial.log')).write_bytes(g.output);cmd=g.command;g.close();g=None
   exported=tmp/(event+'.bytes');transfer(disk,'export','/LOCK.TXT',exported);assert exported.read_bytes()==original.read_bytes()
   g=Guest(a.image.resolve(),str(out.relative_to(ROOT/'build'))+'/'+event+'-reboot',work_disk=disk);g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True);pump(g,1.3);command(g,'cat /LOCK.TXT',b'Old bytes must survive');command(g,'sync',b'[files] sync=ok');(out/(event+'-reboot.serial.log')).write_bytes(g.output);g.close();g=None
   report['checks'].append({'live_readback':b'kind=exited code=0' in result,'same_boot_sync_ok':b'[files] sync=ok' in sync_result,'reboot_readback':True,'name':event,'status':'PASSED','qemu_command':cmd,'old_bytes_sha256':sha(exported),'filter':{'driver':'blkdebug','event':event,'errno':5,'once':True},'resources':base})
   print(event,'PASSED',flush=True)
  report['status']='PASSED'
except Exception as e:report['error']=str(e);raise
finally:
 if g:(out/'failed.serial.log').write_bytes(g.output);g.close()
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report['status'])
