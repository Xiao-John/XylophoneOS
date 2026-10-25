# SPDX-License-Identifier: Apache-2.0
"""P1 offline candidate install -> identical read-only xypm under xsh and dash B2."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from xypm_format import DEFAULT_PROFILE,canonical,load_json,sha_file,require
from xypm_image import Disk,query_image
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes,pump
from process_smoke import resources


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',type=Path,default=ROOT/'build')
    parser.add_argument('--dash-manifest',type=Path,default=ROOT/'.cache/xos_seed/dash/8098a3cc28ff4ce74f5b/manifest.json')
    parser.add_argument('--xypm-build',type=Path,default=ROOT/'build/package_p1/xypm_build.json')
    parser.add_argument('--profile',type=Path,default=ROOT/'config/package/xos_x86_64_static_single_b2_v1.json')
    parser.add_argument('--demo-package',type=Path,default=ROOT/'build/package_p1/demo_cpp.xpk')
    parser.add_argument('--output',type=Path,default=ROOT/'build/package_p1')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    metadata=load_json(args.system/'manifest.json');image=args.system/'xos.img'
    require(sha_file(image)==metadata['artifacts']['xos.img']['sha256'],'system image hash mismatch')
    dash=load_json(args.dash_manifest);dash_elf=ROOT/dash['elf'];require(sha_file(dash_elf)==dash['sha256'],'dash hash mismatch')
    build=load_json(args.xypm_build);require(sha_file(build['package'])==build['sha256'],'xypm package differs from build')
    profile=load_json(args.profile)
    demo=args.demo_package
    report={'status':'failed','system_build_id':metadata['build_id'],'image_sha256':sha_file(image),
            'dash_sha256':dash['sha256'],'xypm_package_sha256':build['sha256'],
            'scope':'P1 host transactions + read-only xypm; common shell behavior, B2 redirection separately',
            'checks':[],'transactions':[],'not_run':['guest_mutating_xypm_P2','signed_repository_P3','threaded_SDK_registration','stress']}
    guest=None
    def host(*arguments):
        result=subprocess.run([sys.executable,str(ROOT/'scripts/xypm.py'),*map(str,arguments),'--profile',str(args.profile)],capture_output=True,text=True)
        require(result.returncode==0,'host xypm failed: '+result.stderr)
        return json.loads(result.stdout)
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p1_guest_') as folder:
            folder=Path(folder);source=folder/'source.img';create_fat32(source,512)
            # Existing dash is intentionally unmanaged. Do not claim ownership by scanning PATH.
            with Disk(source,folder) as disk:
                for name in ('/usr','/usr/bin','/tests','/out'):disk.command('mkdir',name)
                disk.command('import','/usr/bin/dash',dash_elf)
                cases=[('version','--version',0,b'xypm 0.1'),('help','--help',0,b'xypm list'),
                       ('list','list',0,b'xos.xypm 0.1.0-r0'),('info','info xos.xypm',0,b'id: xos.xypm'),
                       ('missing','info friends.missing',1,b'xypm: package not installed'),
                       ('unsupported','install',2,b'xypm: unsupported command')]
                for name,arguments,_,_ in cases:
                    path=folder/(name+'.sh');path.write_text('xypm '+arguments+'\n')
                    disk.command('import','/tests/'+name+'.sh',path)
                redirect=folder/'redirect.sh'
                redirect.write_text('''set -e
xypm list > /out/xypm_list.txt
xypm info friends.missing 2> /out/xypm_error.txt || test "$?" -eq 1
xypm --version
''')
                disk.command('import','/tests/redirect.sh',redirect)
            source_sha=sha_file(source)
            installed=folder/'xypm.img'
            report['transactions'].append(host('install',build['package'],'--image',source,'--output-image',installed,'--offline'))
            both=folder/'both.img'
            report['transactions'].append(host('install',demo,'--image',installed,'--output-image',both,'--offline'))
            require(sha_file(source)==source_sha,'source image changed')
            require(len(host('list','--image',both)['packages'])==2,'wrong installed database count')
            host('verify-installed','--image',both)
            # Clone the boot artifact once so another build cannot substitute a later image.
            boot=folder/'boot.img';boot.write_bytes(image.read_bytes())
            require(sha_file(boot)==report['image_sha256'],'boot snapshot changed')
            def start(disk):
                g=Guest(boot,'package_p1_guest',work_disk=disk)
                g.expect(b'xos64> ',timeout=40);send_bytes(g,b'run\r');g.expect_supervisor(trace=True,timeout=40);pump(g,1.5)
                return g
            guest=start(both);baseline=resources(guest);report['baseline']=baseline
            def command(line,code=0):
                begin=len(guest.output);send_bytes(guest,line.encode()+b'\r')
                guest.expect_supervisor(start=begin,timeout=45)
                data=bytes(guest.output)[begin:]
                statuses=re.findall(rb'kind=exited code=(-?\d+)',data)
                require(bool(statuses) and int(statuses[-1])==code,'unexpected final exit code for '+line+': '+repr(data[-1500:]))
                require(resources(guest)==baseline,'resource drift after '+line)
                return data
            for name,arguments,code,expected in cases:
                direct=command('xypm '+arguments,code)
                via_dash=command('dash /tests/'+name+'.sh',code)
                require(expected in direct and expected in via_dash,'different xsh/dash xypm behavior: '+name)
                report['checks'].append('same_xypm_'+name+'_status_'+str(code))
            data=command('dash /tests/redirect.sh');require(b'xypm 0.1' in data,'stdout not restored after redirects')
            report['checks'].append('dash_B2_redirect_and_stdout_restore')
            data=command('exec-file /usr/bin/external_cpp');require(b'friends.external_cpp' in data,'installed C++ demo did not run')
            report['checks'].append('installed_cpp_runs')
            begin=len(guest.output);send_bytes(guest,b'sync\r');guest.expect(b'[files] sync=ok',start=begin,timeout=30)
            guest.expect_supervisor(start=begin,timeout=30)
            guest.close();(out/'first_boot_serial.log').write_bytes(guest.output);guest=None
            with Disk(both,folder,True) as disk:
                require(disk.export('/out/xypm_list.txt').read_bytes().find(b'xos.xypm 0.1.0-r0')>=0,'redirected list missing')
                require(disk.export('/out/xypm_error.txt').read_bytes()==b'xypm: package not installed\n','redirected stderr incorrect')
            # Upgrade same package explicitly, then remove only the demo; xypm and logs survive.
            upgraded=folder/'upgraded.img'
            report['transactions'].append(host('upgrade',build['package'],'--image',both,'--output-image',upgraded,'--offline'))
            removed=folder/'removed.img'
            report['transactions'].append(host('remove','friends.external_cpp','--image',upgraded,'--output-image',removed,'--offline'))
            require(query_image(removed,profile,'verify-installed')['files']==build['files'],'unexpected remaining ownership')
            guest=start(removed);baseline=resources(guest)
            data=command('xypm list');require(b'xos.xypm 0.1.0-r0' in data and b'friends.external_cpp' not in data,'uninstall not persistent')
            data=command('dash /tests/list.sh');require(b'xos.xypm 0.1.0-r0' in data,'dash query not persistent')
            report['checks'].append('upgrade_remove_reboot_both_shells')
            # The running image is locked; inspect it only after the guest closes.
            guest.close();(out/'second_boot_serial.log').write_bytes(guest.output);guest=None
            with Disk(removed,folder,True) as disk:
                require(disk.info('/usr/bin/external_cpp') is None,'demo file survived uninstall')
                require(b'xos.xypm' in disk.export('/out/xypm_list.txt').read_bytes(),'user log deleted by uninstall')
            report['checks'].append('user_output_preserved')
            report['final_image_sha256']=sha_file(removed);report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-6000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close();(out/'failed_serial.log').write_bytes(guest.output)
        (out/'guest_report.json').write_bytes(canonical(report))
    print(canonical(report).decode())
if __name__=='__main__':main()
