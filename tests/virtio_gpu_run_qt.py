#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute an unchanged acceptance runner with a task-local root and real GPU VM.

Only the runner's ROOT assignment changes, so output remains in this worktree.
All assertions/input injection remain intact. Record original/executed source hashes.
"""
import argparse,hashlib,json,re,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import boot_smoke
p=argparse.ArgumentParser()
p.add_argument('--runner',type=Path,required=True)
p.add_argument('--backend',choices=['virtio','vbe'],default='virtio')
a,rest=p.parse_known_args();runner=a.runner.resolve();source=runner.read_text()
updated,count=re.subn(r'^ROOT\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[1\]',lambda _:"ROOT=Path("+repr(str(ROOT))+")",source,count=1,flags=re.M)
assert count==1,'runner root assignment not recognized'
original=boot_smoke.qemu_command;commands=[]
def qemu(*args,**kw):
 cmd=original(*args,**kw)
 if a.backend=='virtio':cmd[cmd.index('-vga')+1]='none';cmd+=['-device','virtio-gpu-pci,id=vgpu,disable-legacy=on']
 commands.append(cmd);return cmd
sys.argv=[str(runner),*rest]
try:
 with patch.object(boot_smoke,'qemu_command',qemu):exec(compile(updated,str(runner),'exec'),{'__name__':'__main__','__file__':str(runner)})
finally:
 key='--output' if '--output' in rest else '--report';target=Path(rest[rest.index(key)+1]);target=target/'backend_execution.json' if key=='--output' else target.with_suffix('.backend.json');target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps({'runner':str(runner),'runner_sha256':hashlib.sha256(source.encode()).hexdigest(),'executed_sha256':hashlib.sha256(updated.encode()).hexdigest(),'root_override':str(ROOT),'backend':a.backend,'qemu_commands':commands},indent=2)+'\n')
