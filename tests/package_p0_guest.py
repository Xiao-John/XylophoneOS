# SPDX-License-Identifier: Apache-2.0
"""Run new independent package payloads on a frozen XOS image and a fresh test disk.
Uses the existing file bridge, not a package installer or package database.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
from xpkg_format import DEFAULT_PROFILE, canonical, load_json, require, sha_file, verify_package
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-dir',type=Path,default=ROOT/'build/releases/0.0.1-1024')
    parser.add_argument('--artifacts',type=Path,default=ROOT/'build/package_p0')
    args=parser.parse_args()
    system=args.system_dir.resolve(); artifacts=args.artifacts.resolve()
    profile=load_json(DEFAULT_PROFILE)
    metadata=load_json(system/'system_manifest.json')
    image=system/'xos.img'
    require(metadata['build_id'] in profile['verified_system_builds'],'system not registered for profile')
    require(sha_file(image)==metadata['artifacts']['xos.img']['sha256'],'image differs from receipt')
    helper=ROOT/'build/work_disk_host'
    require(helper.is_file(),'existing work_disk_host required; this runner never rebuilds shared tools')
    report={'status':'failed','scope':'P0 payload transfer via existing bridge; no package installation DB',
            'system_build_id':metadata['build_id'],'image_sha256':sha_file(image),
            'profile':profile['id'],'host_bridge_sha256':sha_file(helper),'checks':[]}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_package_guest_') as folder:
            root=Path(folder);stage=root/'stage';stage.mkdir()
            for language in ('c','cpp'):
                def sink(event,item,data):
                    dest=stage/item['path']
                    if event=='begin':
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        with dest.open('xb'):pass
                    elif event=='data':
                        with dest.open('ab') as output:output.write(data)
                value=verify_package(artifacts/language/'app.xpk',profile,sink=sink)
                report['checks'].append({'name':'package_'+language,'sha256':value['sha256'],'files':value['payload_files']})
            disk=root/'test.img';create_fat32(disk,512)
            directories={parent.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file() for parent in p.parents if parent!=stage and parent.is_relative_to(stage)}
            for name in sorted(directories,key=lambda x:(x.count('/'),x)):
                subprocess.run([str(helper),str(disk),'mkdir','/'+name],check=True,stdout=subprocess.DEVNULL)
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    subprocess.run([str(helper),str(disk),'import','/'+path.relative_to(stage).as_posix(),str(path)],check=True,stdout=subprocess.DEVNULL)
            guest=Guest(image,'package_p0_guest',work_disk=disk)
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r')
            guest.expect_supervisor(timeout=40);pump(guest,2)
            def command(line):
                start=len(guest.output);send_bytes(guest,line.encode()+b'\r')
                guest.expect_supervisor(start=start,timeout=40)
                return bytes(guest.output)[start:]
            def resources():
                data=command('stats')
                match=re.search(rb'\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)',data)
                require(match is not None,'missing resource counters')
                return list(map(int,match.groups()))
            baseline=resources();report['resource_baseline']=baseline
            for language in ('c','cpp'):
                data=command('exec-file /usr/bin/external_'+language)
                require(('Hello from XOS package: friends.external_'+language).encode() in data,'missing application output')
                require(b'kind=exited code=0' in data,'not normal exit 0')
                after=resources();require(after==baseline,'resources not returned to baseline')
                report['checks'].append({'name':'guest_'+language,'status':'passed','resource_after':after})
            require(b'[files] sync=ok' in command('sync'),'sync failed')
            report['work_disk_sha256_after_sync']=sha_file(disk)
            report['status']='passed'
    finally:
        if guest:
            guest.close()
            (artifacts/'guest_serial.log').write_bytes(guest.output)
        (artifacts/'guest_report.json').write_bytes(canonical(report))
    print(canonical(report).decode())


if __name__=='__main__':main()
