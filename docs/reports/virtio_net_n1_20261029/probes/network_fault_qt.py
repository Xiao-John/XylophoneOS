#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Transparent supplemental runner: real jumbo NIC failure, then Qt in the SAME boot."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
original=ROOT/'tests/virtio_net_acceptance.py';source=original.read_text()
qt=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e17/build/qt_e17/final_gui/qt_demo.elf')
access=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-network-abi/build/network_abi/access_fault.elf')
assert qt.is_file() and access.is_file()
source=source.replace('conn.settimeout(15)','conn.settimeout(120)')
needle="transfer(disk,'import','/bin/access.elf',a.access_payload)"
source=source.replace(needle,needle+";transfer(disk,'import','/bin/gui.elf',Path("+repr(str(qt))+"))")
needle=" if a.access_payload:\n  from process_smoke import command,resources"
extra=''' if a.access_payload:
  import re
  from process_smoke import command,resources
  command(g,'demo quiet',b'demo tasks')
  pre=resources(g)
  started=command(g,'display-start',b'result=0')
  service=int(re.search(rb'pid=(\\d+)',started)[1])
  g.expect(b'[display-service] ready')
  with_service=resources(g)
  start=len(g.output);send_bytes(g,b'exec-file /bin/gui.elf pixels\\r')
  g.expect(b'QT_GUI_PIXEL_REFERENCE_READY',start=start,timeout=90)
  g.qmp('screendump',{'filename':str(out/'after-network-fault.ppm')})
  from PIL import Image
  Image.open(out/'after-network-fault.ppm').save(out/'after-network-fault.png')
  for down in (True,False):g.qmp('input-send-event',{'events':[{'type':'key','data':{'down':down,'key':{'type':'qcode','data':'esc'}}}]})
  g.expect(b'kind=exited code=0',start=start,timeout=30);g.expect(b'xsh> ',start=start)
  assert resources(g)==with_service
  command(g,'exec gfxdemo stop',b'kind=exited code=0')
  command(g,f'wait {service}',b'kind=exited code=0')
  assert resources(g)==pre
  report['same_boot_Qt_after_network_failure']='PASSED'
  report['Qt_pre_resources']=pre
  report['Qt_with_display_service_resources']=with_service
  report['Qt_ELF_sha256']=sha(Path('''+repr(str(qt))+''').read_bytes())
'''
assert needle in source;source=source.replace(needle,extra+needle)
run=ROOT/'build/network/network_fault_qt_executed_runner.py';run.write_text(source)
receipt={'original_runner_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'executed_runner_sha256':hashlib.sha256(source.encode()).hexdigest(),'adaptations':['import source-matched existing QtGui ELF into isolated FAT','after actual NIC jumbo fail/reset and run: start Display Service, render Qt pixels, real QMP screenshot/Escape, stop service with exact resources','host packet socket timeout extended for real GUI workload'],'image_manifest':str(ROOT/'build/network/qualified_system/manifest.json')}
(ROOT/'build/network/network_fault_qt_adapter_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
sys.argv=[str(original),'--system',str(ROOT/'build/network/qualified_system'),'--output',str(ROOT/'build/network/qualified_gates/jumbo_qt'),'--mode','jumbo','--access-payload',str(access)]
exec(compile(source,str(run),'exec'),{'__file__':str(original),'__name__':'__main__'})
