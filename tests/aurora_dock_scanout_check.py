#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare the six fixed 800x600 Midnight Dock buttons in two guest scanouts."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops

parser=argparse.ArgumentParser()
for name in ('before','after','output'):parser.add_argument('--'+name,type=Path,required=True)
args=parser.parse_args()
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
before=Image.open(args.before).convert('RGB');after=Image.open(args.after).convert('RGB')
if before.size!=(800,600) or after.size!=(800,600):raise SystemExit('expected 800x600 guest scanouts')
diff=ImageChops.difference(before,after)
checks=[]
for name,x in zip(('home','apps','studio','settings','quality','hide'),(100,202,304,405,506,608)):
    crop=diff.crop((x,538,x+88,574))
    changed=sum(1 for pixel in crop.get_flattened_data() if max(pixel)>20)
    checks.append({'name':name,'changed_pixels':changed,'status':'PASS' if changed>=50 else 'FAIL'})
report={'status':'PASSED' if all(c['status']=='PASS' for c in checks) else 'FAILED',
        'before_sha256':sha(args.before),'after_sha256':sha(args.after),'checks':checks,
        'scope':'fixed 800x600 Midnight Dock; screenshot difference, not a semantic or visual-quality rating'}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
print(report['status'],len(checks),'button regions')
if report['status']!='PASSED':raise SystemExit(1)
