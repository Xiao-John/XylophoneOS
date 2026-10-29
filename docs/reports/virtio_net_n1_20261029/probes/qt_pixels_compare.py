#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare actual same-boot post-network-fault QEMU scanout with guest QImage bytes."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(ROOT/'scripts'))
from work_disk import transfer
out=ROOT/'build/network/qualified_gates/jumbo_qt';reference=out/'guest_qimage.bin'
transfer(out/'probe_disk.img','export','/qtframe.bin',reference)
a=Image.open(out/'after-network-fault.png').convert('RGB');b=Image.frombytes('RGB',(800,600),reference.read_bytes(),'raw','BGRX')
assert a.size==(800,600) and a.tobytes()==b.tobytes()
(out/'pixel_comparison.json').write_text(json.dumps({'status':'PASSED','compared_RGB_bytes':len(a.tobytes()),'RGB_sha256':hashlib.sha256(a.tobytes()).hexdigest(),'guest_QImage_sha256':hashlib.sha256(reference.read_bytes()).hexdigest()},indent=2)+'\n')
print('PASSED 1,440,000 actual RGB bytes after network failure')
