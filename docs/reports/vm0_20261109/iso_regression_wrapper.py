import hashlib, json, os, sys
from pathlib import Path
root=Path('/workspace/XylophoneOS'); system=root/'build/vm0/final'; output=root/'build/vm0/regression_final'; output.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(root/'tests'),str(root/'scripts')]
for p in system.iterdir():
 if p.name!='manifest.json' and not (output/p.name).exists(): (output/p.name).symlink_to(p)
image=system/'xos-install.iso'; (output/'xos.img').symlink_to(image)
m=json.loads((system/'manifest.json').read_text());m['artifacts']['xos.img']={'sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
(output/'manifest.json').write_text(json.dumps(m))
import process_smoke, file_smoke, boot_smoke, kernel_smoke
class Overlay:
 def __fspath__(self): return str(root)
 def __truediv__(self,part):
  if part=='build': return output
  if str(part).startswith('build/'): return output/str(part)[6:]
  return root/part
base=Overlay()
for mod in (process_smoke,file_smoke,boot_smoke,kernel_smoke): mod.ROOT=base
old=boot_smoke.Guest
class IsoGuest(old):
 def __init__(self,image,name,**kwargs):
  kwargs['iso']=True
  super().__init__(image,name,**kwargs)
process_smoke.Guest=IsoGuest; file_smoke.Guest=IsoGuest
process_smoke.main();file_smoke.main()
