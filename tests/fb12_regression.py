#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run existing E04/E05 checks against the isolated FB1/FB2 system build."""
import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from make_work_disk import make_image
import boot_smoke,kernel_smoke,process_smoke,file_smoke
class Overlay:
 def __fspath__(self):return os.fspath(ROOT)
 def __truediv__(self,part):
  if part=='build':return Path(os.environ.get('FB12_SYSTEM',ROOT/'build/fb12/system'))
  if str(part).startswith('build/'):return Path(os.environ.get('FB12_SYSTEM',ROOT/'build/fb12/system'))/str(part)[6:]
  return ROOT/part
root=Overlay()
for module in (boot_smoke,kernel_smoke,process_smoke,file_smoke):module.ROOT=root
original=boot_smoke.Guest
with tempfile.TemporaryDirectory(prefix='xos_fb12_e04_') as tmp:
 disk=Path(tmp)/'work.img';disk.write_bytes(make_image())
 def with_disk(image,name,**kwargs):
  kwargs.setdefault('work_disk',disk);return original(image,name,**kwargs)
 process_smoke.Guest=with_disk
 process_smoke.main()
file_smoke.main()
