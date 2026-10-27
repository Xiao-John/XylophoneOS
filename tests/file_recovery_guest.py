# SPDX-License-Identifier: Apache-2.0
"""Real boot recovery controls and failed-closed corrupt journal on private FAT images."""
import argparse,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for path in ['scripts','tests']:sys.path.insert(0,str(ROOT/path))
from boot_smoke import Guest
from task_smoke import send_bytes,pump
from process_smoke import resources,command
from make_work_disk import make_image
from xypm_image import Disk
from xypm_format import sha_file

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--system',type=Path,default=ROOT/'build/audit_01/system');args=parser.parse_args()
    out=ROOT/'build/audit_01/recovery_guest';out.mkdir(parents=True,exist_ok=True)
    system=json.loads((args.system/'manifest.json').read_text());image=args.system/'xos.img'
    assert sha_file(image)==system['artifacts']['xos.img']['sha256']
    report={'status':'failed','build_id':system['build_id'],'image_sha256':sha_file(image),'checks':[]}
    guest=None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_recovery_guest_') as temp:
            temp=Path(temp)
            for mode in ['orphan','rollback','committed','corrupt']:
                disk=temp/(mode+'.img');disk.write_bytes(make_image())
                inputs={'XOSTMP.TMP':b'staged bytes'}
                if mode!='orphan':inputs.update({'XOSJRNL.TMP':b'target.txt\0','XOSBAK.TMP':b'old bytes'})
                if mode!='rollback':inputs['target.txt']=b'new bytes'
                if mode=='corrupt':inputs['XOSJRNL.TMP']=b'invalid without terminator'
                with Disk(disk,temp) as backend:
                    for i,(path,body) in enumerate(inputs.items()):
                        source=temp/(mode+str(i));source.write_bytes(body);backend.command('import','/'+path,source)
                guest=Guest(image,'recovery_'+mode,work_disk=disk)
                guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(timeout=40);pump(guest,1.5)
                baseline=resources(guest)
                if mode=='corrupt':
                    command(guest,'stat target.txt',b'error=-7')
                    command(guest,'mkdir /blocked',b'error=-7')
                else:
                    command(guest,'cat target.txt',b'old bytes' if mode=='rollback' else b'new bytes')
                    command(guest,'sync',b'[files] sync=ok')
                assert resources(guest)==baseline
                guest.close();(out/(mode+'.log')).write_bytes(guest.output);guest=None
                with Disk(disk,temp,True) as backend:
                    if mode=='corrupt':
                        for path,body in inputs.items():assert backend.export('/'+path).read_bytes()==body
                        assert backend.info('/blocked') is None
                    else:
                        for path in ['XOSTMP.TMP','XOSJRNL.TMP','XOSBAK.TMP']:assert backend.info('/'+path) is None
                        assert backend.export('/target.txt').read_bytes()==(b'old bytes' if mode=='rollback' else b'new bytes')
                report['checks'].append({'name':mode,'passed':True,'resources':baseline})
                if mode=='rollback':
                    guest=Guest(image,'recovery_reboot',work_disk=disk)
                    guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(timeout=40);pump(guest,1.5)
                    command(guest,'cat target.txt',b'old bytes');guest.close();guest=None
                    report['checks'].append({'name':'rollback_idempotent_second_boot','passed':True})
        report['status']='passed'
    except Exception as error:
        report['error']=str(error);raise
    finally:
        if guest:guest.close();(out/'failed.log').write_bytes(guest.output)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
