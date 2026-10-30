# SPDX-License-Identifier: Apache-2.0
"""Bind real Pillow tests and dependency observations to a fresh XOS guest."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from stage_cpython import stage_cpython
from task_smoke import send_bytes, pump
from work_disk import transfer

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()

def treecopy(source,disk,dest,only_py=False):
    for path in sorted(source.rglob('*')):
        relative=path.relative_to(source)
        if any(part in {'__pycache__','.git','node_modules','dist','build'} for part in relative.parts):continue
        target=dest+'/'+relative.as_posix()
        if path.is_dir():transfer(disk,'mkdir',target)
        elif path.is_file() and (not only_py or path.suffix in {'.py','.json','.txt'}):transfer(disk,'import',target,path)

def run(guest,command,timeout=180):
    start=len(guest.output);send_bytes(guest,command.encode()+b'\r')
    guest.expect(b'[wait] pid=',start=start,timeout=timeout)
    guest.expect_supervisor(start=guest.output.find(b'[wait] pid=',start),timeout=30)
    pump(guest,.3)
    return re.sub(r'\x1b\[[0-9;]*m','',bytes(guest.output[start:]).decode('utf-8','replace'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);parser.add_argument('--image',type=Path,required=True);parser.add_argument('--dash',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--extra-probe',type=Path);parser.add_argument('--dependencies',type=Path);parser.add_argument('--localpilot',type=Path);args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);disk=out/'work.img';create_fat32(disk,2048)
    report={'status':'FAILED','checks':[],'image_sha256':sha(args.image),'dash_sha256':sha(args.dash),'probe_sha256':sha(ROOT/'tests/fixtures/pillow_static/imaging.py'),'work':str(args.work.resolve()),'scope':'single-threaded static Pillow core; concurrency probes are diagnostic only; not full Python/LocalPilot/API qualification'}
    for folder in ['/work','/work/deps','/work/localpilot']:transfer(disk,'mkdir',folder)
    stage,manifest=stage_cpython(args.work);treecopy(stage,disk,'');report['stage']=manifest
    transfer(disk,'import','/usr/bin/dash',args.dash)
    transfer(disk,'import','/work/original_threads.py',ROOT/'tests/fixtures/cpython_t3_py/threading_core.py')
    transfer(disk,'import','/usr/bin/xos-diag',args.image.parent/'user_xos_diag.image.elf')
    for file in (ROOT/'tests/fixtures/pillow_static').glob('*.py'):transfer(disk,'import','/work/'+file.name,file)
    for name,script in [('success','(exec /usr/bin/python3 /work/imaging.py single); echo PILLOW_DASH:$?\n'),('failure','(exec /usr/bin/python3 /work/failure.py); echo PILLOW_DASH_FAIL:$?\n'),('thread_baseline','(exec /usr/bin/python3 /work/thread_allocator.py); echo BASELINE_DASH:$?\n'),('thread_pillow','(exec /usr/bin/python3 /work/imaging.py); echo THREAD_PILLOW_DASH:$?\n'),('original_threads','(exec /usr/bin/python3 /work/original_threads.py); echo ORIGINAL_DASH:$?\n'),('thread_diagnosed','(exec /usr/bin/xos-diag /usr/bin/python3 /work/imaging.py); echo DIAG_DASH:$?\n')]:
        path=out/(name+'.sh');path.write_text(script);transfer(disk,'import','/work/'+name+'.sh',path)
    if args.dependencies:
        treecopy(args.dependencies/'site-packages',disk,'/work/deps',True)
    if args.localpilot:
        lp=args.localpilot.resolve();report['localpilot_sha']=subprocess.check_output(['git','-C',str(lp),'rev-parse','HEAD'],text=True).strip()
        for name in ['agent','computer','localpilot_api','localpilot_service','localpilot_plugins','localpilot_channels']:
            transfer(disk,'mkdir','/work/localpilot/'+name);treecopy(lp/name,disk,'/work/localpilot/'+name,True)
        for name in ['catalog.py','recommender.py','hardware.py']:transfer(disk,'import','/work/localpilot/'+name,lp/name)
    if args.extra_probe:
        transfer(disk,'import','/work/extra.py',args.extra_probe);report['extra_probe_sha256']=sha(args.extra_probe)
    report['disk_before_sha256']=sha(disk);guest=None
    try:
        guest=Guest(args.image,'modern2-python/'+out.name,work_disk=disk);report['qemu_command']=guest.command;report['qemu_version']=subprocess.check_output([guest.command[0],'--version'],text=True).splitlines()[0]
        guest.expect(b'xos64> ',timeout=30);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1)
        baseline=resources(guest);report['resources_before']=baseline
        cases=[('xsh_success','python3 /work/imaging.py single','IMAGING_OK:',0),('xsh_error','python3 /work/failure.py','ValueError',1),('xsh_recovery','python3 /work/imaging.py single','IMAGING_OK:',0),('dash_success','dash /work/success.sh','PILLOW_DASH:0',0),('dash_error','dash /work/failure.sh','PILLOW_DASH_FAIL:1',0)]
        for name,command,marker,exitcode in cases:
            text=run(guest,command);(out/(name+'.log')).write_text(text);after=resources(guest)
            report['checks'].append({'name':name,'status':'PASSED' if marker in text and 'kind=exited code='+str(exitcode) in text and after==baseline else 'FAILED','resources_after':after})
        for name,command,marker in [('xsh_original_threads','python3 /work/original_threads.py','T3_PY_CORE_OK'),('dash_original_threads','dash /work/original_threads.sh','ORIGINAL_DASH:0'),('xsh_thread_pillow','python3 /work/imaging.py','IMAGING_OK:'),('dash_thread_diagnosed','dash /work/thread_diagnosed.sh','DIAG_DASH:0'),('xsh_thread_baseline','python3 /work/thread_allocator.py','BASELINE_THREADS_OK'),('dash_thread_baseline','dash /work/thread_baseline.sh','BASELINE_DASH:0'),('dash_thread_pillow','dash /work/thread_pillow.sh','THREAD_PILLOW_DASH:0')]:
            text=run(guest,command);(out/(name+'.log')).write_text(text)
            report.setdefault('thread_diagnostics',[]).append({'name':name,'status':'PASSED' if marker in text and resources(guest)==baseline else 'FAILED','resources_after':resources(guest)})
        if args.extra_probe:
            text=run(guest,'python3 /work/extra.py',240);(out/'dependencies.log').write_text(text)
            report['dependency_observations']=[json.loads(line.split('DEPCHAIN:',1)[1]) for line in text.splitlines() if line.startswith('DEPCHAIN:')]
            report['checks'].append({'name':'original_dependency_observations','status':'PASSED' if 'DEPCHAIN_DONE' in text and 'kind=exited code=0' in text and resources(guest)==baseline else 'FAILED'})
        report['resources_after']=resources(guest)
        start=len(guest.output);send_bytes(guest,b'sync\r');guest.expect(b'sync=ok',start=start);guest.expect_supervisor(start=start)
        report['status']='PASSED_CORE_SUBSET' if all(row['status']=='PASSED' for row in report['checks']) else 'FAILED'
        report['thread_qualification']='NOT_QUALIFIED_DIAGNOSTIC_ONLY'
    except BaseException as error:report['error']=repr(error)
    finally:
        if guest:
            guest.close();shutil.copyfile(ROOT/f'build/{guest.name}_serial.log',out/'serial.log');shutil.copyfile(ROOT/f'build/{guest.name}_qemu.log',out/'qemu.log')
        report['disk_after_sha256']=sha(disk)
        if guest:
            bundles=set(re.findall(rb'\[fault-bundle\] saved (/FAULTS/[0-9a-f]{32})',bytes(guest.output)))
            for bundle in bundles:
                target=out/('fault-'+bundle.decode().rsplit('/',1)[1]);target.mkdir()
                for name in ['report.json','image.json','context.json','manifest.json']:
                    transfer(disk,'export',bundle.decode()+'/'+name,target/name)
            report['fault_bundles']=[path.name for path in sorted(out.glob('fault-*'))]
        for format in ['png','bmp']:
            path=out/('guest.'+format)
            try:transfer(disk,'export','/work/pillow-'+format+'.bin',path);report[format+'_sha256']=sha(path)
            except BaseException as error:report[format+'_export_error']=repr(error)
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'stage','dependency_observations'}},indent=2));raise SystemExit(report['status']!='PASSED_CORE_SUBSET')
if __name__=='__main__':main()
