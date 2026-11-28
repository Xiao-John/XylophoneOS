#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run genuine WebCore DOM/CSS geometry and paint fixtures inside XOS."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import command,resources
from task_smoke import send_bytes,pump
from work_disk import transfer


def digest(path):
    with path.open('rb') as stream: return file_digest(stream,'sha256').hexdigest()


def ppm(path):
    with path.open('rb') as stream:
        if [stream.readline().strip() for _ in range(3)] != [b'P6',b'320 180',b'255']:
            raise ValueError('unexpected WebCore output dimensions')
        pixels=stream.read()
    if len(pixels)!=320*180*3: raise ValueError('truncated WebCore PPM')
    return pixels


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('system','bundle','output'):
        parser.add_argument('--'+name,required=True,type=lambda value:Path(value).resolve())
    args=parser.parse_args()
    system=json.loads((args.system/'manifest.json').read_bytes())
    bundle=json.loads((args.bundle/'manifest.json').read_bytes())
    if bundle['status']!='clarke_webcore_browser_linked': raise ValueError('require the actual linked WebCore browser')
    for name in ('dom_css.elf','DejaVuSans.ttf'):
        if digest(args.bundle/name)!=bundle['artifacts'][name]: raise ValueError('bundle artifact mismatch: '+name)
    image=args.system/'xos-install.iso'
    if digest(image)!=system['artifacts'][image.name]['sha256']: raise ValueError('ISO mismatch')
    cases=('box','flex','grid','cascade','clip','text')
    fixtures=ROOT/'tests/fixtures/webkit/dom_css'
    for name in cases:
        path=fixtures/(name+'.html')
        if digest(path)!=bundle['inputs'][str(path.relative_to(ROOT))]: raise ValueError('fixture changed: '+name)
    args.output.mkdir(parents=True,exist_ok=False)
    disk=args.output/'dom-css.img';create_fat32(disk,512)
    for directory in ('/usr','/usr/share','/usr/share/fonts','/usr/share/fonts/clarke','/fixtures','/results'):
        transfer(disk,'mkdir',directory)
    transfer(disk,'import','/dom_css.elf',args.bundle/'dom_css.elf')
    transfer(disk,'import','/usr/share/fonts/clarke/DejaVuSans.ttf',args.bundle/'DejaVuSans.ttf')
    for name in cases: transfer(disk,'import','/fixtures/'+name+'.html',fixtures/(name+'.html'))
    wrong=args.output/'wrong.html'
    body=(fixtures/'box.html').read_bytes()
    if body.count(b'background:red')!=1: raise ValueError('negative paint mutation is ambiguous')
    wrong.write_bytes(body.replace(b'background:red',b'background:blue'))
    transfer(disk,'import','/fixtures/wrong.html',wrong)
    report={'status':'failed','runner_sha256':digest(Path(__file__)),'system_manifest_sha256':digest(args.system/'manifest.json'),
            'bundle_manifest_sha256':digest(args.bundle/'manifest.json'),'elf_sha256':digest(args.bundle/'dom_css.elf'),'cases':[]}
    guest=None
    try:
        guest=Guest(image,'clarke_dom_css',work_disk=disk,log_dir=args.output)
        guest.expect(b'xos64> ',timeout=30);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=30)
        command(guest,'demo quiet',b'demo tasks')
        baseline=resources(guest);report['resources_before']=baseline
        for name in (*cases,'wrong'):
            selected='box' if name=='wrong' else name
            output=command(guest,f'exec-file /dom_css.elf {selected} /fixtures/{name}.html /results/{name}.ppm',b'[wait] pid=',timeout=120)
            exits=[int(value) for value in re.findall(rb'kind=exited code=(-?\d+)',output)]
            markers=re.findall(rb'XOS_WEBCORE_DOM_CSS_PASS case=([a-z]+) rectangles=(\d+) pixels=(\d+) viewport=320x180',output)
            after=resources(guest)
            report['cases'].append({'name':name,'exit_codes':exits,'markers':[list(map(lambda value:value.decode(),match)) for match in markers],
                                    'resources_after':after})
            if exits!=([11] if name=='wrong' else [0]) or len(markers)!=(0 if name=='wrong' else 1) or after!=baseline:
                raise AssertionError('DOM/CSS geometry, pixels or resource recovery failed: '+repr(output[-1800:]))
        command(guest,'sync',b'[files] sync=ok',timeout=30)
        guest.close();(args.output/'guest.serial.log').write_bytes(guest.output);guest=None
        report['ppm']={}
        for name in cases:
            target=args.output/(name+'.ppm');transfer(disk,'export','/results/'+name+'.ppm',target)
            pixels=ppm(target)
            if pixels==bytes((255,255,255))*(320*180): raise AssertionError('blank WebCore raster')
            report['ppm'][name]={'sha256':digest(target),'bytes':len(pixels)}
        report['status']='passed'
    finally:
        if guest:
            guest.close();(args.output/'guest.serial.log').write_bytes(guest.output)
        disk.unlink(missing_ok=True)
        (args.output/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        files={path.name:digest(path) for path in args.output.iterdir() if path.is_file() and path.name!='manifest.json'}
        (args.output/'manifest.json').write_text(json.dumps({'version':1,'files':files},indent=2,sort_keys=True)+'\n')
    print(report['status'])


if __name__=='__main__':main()
