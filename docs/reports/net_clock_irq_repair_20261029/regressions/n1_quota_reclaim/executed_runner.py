#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Frozen supplemental real-guest probe: failed DMA allocations do not accumulate."""
import json,os,re,socket,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_runs/n1_quota_reclaim');sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import boot_smoke
from boot_smoke import Guest
from task_smoke import send_bytes
out=ROOT/'build/network/qualified_gates/quota_reclaim';out.mkdir(parents=True,exist_ok=False)
server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
original=boot_smoke.qemu_command
def command(*args,**kwargs):
 return original(*args,**kwargs)+['-netdev',f'socket,id=net,connect=127.0.0.1:{server.getsockname()[1]}','-device','virtio-net-pci,netdev=net,disable-legacy=on,mac=52:54:00:12:34:56']
g=None;report={'status':'FAILED'}
try:
 with patch.object(boot_smoke,'qemu_command',command):g=Guest(ROOT/'build/xos-install.iso','network/qualified_gates/quota_reclaim/guest')
 g.expect(b'xos64> ',timeout=40)
 def free():
  start=len(g.output);send_bytes(g,b'mem\r');g.expect(b'xos64> ',start=start)
  return int(re.search(rb' free=(\d+)',bytes(g.output[start:]))[1])
 counts=[free()]
 for _ in range(3):
  start=len(g.output);send_bytes(g,b'net-test\r');g.expect(b'net-test unavailable_or_failed',start=start);g.expect(b'xos64> ',start=start)
  assert b'features_queue_or_DMA_failure' in g.output[start:]
  counts.append(free())
 # First BAR mapping may consume one bounded kernel page table, never DMA leakage.
 assert 0<=counts[0]-counts[1]<=1 and counts[1:]==[counts[1]]*3,counts
 report.update(status='PASSED',free_pages=counts,qemu_command=g.command)
finally:
 if g:(out/'guest.serial.log').write_bytes(g.output);g.close()
 server.close();(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(report)
