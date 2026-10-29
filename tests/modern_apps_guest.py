# SPDX-License-Identifier: Apache-2.0
"""Run pinned JS and Python compatibility probes in a real isolated XOS guest."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
from boot_smoke import Guest
from cpython_py1_smoke import install_stage
from make_work_disk import create_fat32
from process_smoke import resources
from stage_cpython import stage_cpython
from task_smoke import send_bytes,pump
from work_disk import transfer

def run(guest,command,timeout=90):
 start=len(guest.output);send_bytes(guest,command.encode()+b'\r')
 guest.expect(b'[wait] pid=',start=start,timeout=timeout)
 guest.expect_supervisor(start=guest.output.find(b'[wait] pid=',start),timeout=30)
 pump(guest,.2)
 return re.sub(r'\x1b\[[0-9;]*m','',bytes(guest.output[start:]).decode('utf-8','replace'))

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def treecopy(source,disk,dest,only_py=False):
 for p in sorted(source.rglob('*')):
  rel=p.relative_to(source)
  if any(x in {'__pycache__','.git','node_modules','dist','build'} for x in rel.parts):continue
  target=dest+'/'+rel.as_posix()
  if p.is_dir():transfer(disk,'mkdir',target)
  elif p.is_file() and (not only_py or p.suffix in {'.py','.json','.txt'}):transfer(disk,'import',target,p)
def main():
 p=argparse.ArgumentParser();p.add_argument('--python-work',type=Path);p.add_argument('--localpilot',type=Path);p.add_argument('--image',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);disk=out/'work.img';create_fat32(disk,2048)
 for folder in ['/usr','/usr/bin','/work','/work/js','/work/deps','/work/localpilot','/work/licenses']:transfer(disk,'mkdir',folder)
 js=ROOT/'build/modern_apps/quickjs/js_probe.elf';strip=out/'js_probe'
 subprocess.run(['x86_64-elf-strip','-o',str(strip),str(js)],check=True);transfer(disk,'import','/usr/bin/jsprobe',strip)
 for fixture in (ROOT/'tests/fixtures/modern_apps').glob('*.js'):transfer(disk,'import','/work/js/'+fixture.name,fixture)
 transfer(disk,'import','/work/js/code.js',ROOT/'build/modern_apps/probes/code_extension_iframe.js')
 report={'status':'FAILED','scope':'compatibility observations, not browser/LocalPilot/Code qualification','image_sha256':sha(a.image),'js_elf_sha256':sha(js),'js_stripped_sha256':sha(strip),'checks':[]}
 if a.localpilot:
  lp=a.localpilot.resolve();report['localpilot_sha']=subprocess.check_output(['git','-C',str(lp),'rev-parse','HEAD'],text=True).strip()
  for name in ['agent','computer','localpilot_api','localpilot_service','localpilot_plugins','localpilot_channels']:
   transfer(disk,'mkdir','/work/localpilot/'+name);treecopy(lp/name,disk,'/work/localpilot/'+name,True)
  for name in ['catalog.py','recommender.py','hardware.py']:transfer(disk,'import','/work/localpilot/'+name,lp/name)
  bundle=next((lp/'desktop/dist/assets').glob('index-*.js'));transfer(disk,'import','/work/js/localpilot.mjs',bundle);report['frontend_bundle_sha256']=sha(bundle)
 if a.python_work:
  stage,manifest=stage_cpython(a.python_work)
  for directory in sorted((x for x in stage.rglob('*') if x.is_dir()),key=lambda x:len(x.parts)):
   relative=directory.relative_to(stage).as_posix()
   if relative not in {'usr','usr/bin'}:transfer(disk,'mkdir','/'+relative)
  for file in sorted(stage.rglob('*')):
   if file.is_file():transfer(disk,'import','/'+file.relative_to(stage).as_posix(),file)
  report['python_stage']=manifest
  treecopy(ROOT/'build/modern_apps/python_deps/site-packages',disk,'/work/deps',True)
  for name,folder in [('psutil','psutil-7.1.3/psutil'),('PIL','pillow-11.3.0/src/PIL')]:
   transfer(disk,'mkdir','/work/deps/'+name);treecopy(ROOT/'build/modern_apps/python_deps/native-source'/folder,disk,'/work/deps/'+name,True)
  transfer(disk,'import','/work/python_probe.py',ROOT/'tests/fixtures/modern_apps/python_probe.py')
 treecopy(ROOT/'licenses/modern_apps',disk,'/work/licenses')
 report['disk_before_sha256']=sha(disk)
 guest=None
 try:
  guest=Guest(a.image,'modern_apps_'+out.name,work_disk=disk);report['qemu_command']=guest.command
  report['qemu_version']=subprocess.check_output([guest.command[0],'--version'],text=True).splitlines()[0]
  guest.expect(b'xos64> ',timeout=30);start=len(guest.output);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,start=start,timeout=40);pump(guest,1)
  baseline=resources(guest);report['resources_before']=baseline
  cases=[('language','language.js','LANGUAGE_OK','0'),('js_exception','exception.js','intentional exception probe','1'),('js_rejection','rejection.js','intentional rejected Promise','1'),('js_interrupt','loop.js','interrupted','1'),('language_after_interrupt','language.js','LANGUAGE_OK','0'),('js_memory_limit','memory.js','out of memory','1'),('js_stack_limit','stack.js','stack overflow','1'),('web_capabilities','web_capabilities.js','"document":"undefined"','0'),('code_actual_iframe','code.js',"'URL' is not defined",'1')]
  if a.localpilot:cases.append(('localpilot_actual_bundle','localpilot.mjs',"'document' is not defined",'1'))
  for name,file,marker,exitcode in cases:
   text=run(guest,'jsprobe /work/js/'+file,timeout=180);after=resources(guest)
   (out/(name+'.log')).write_text(text)
   report['checks'].append({'name':name,'harness_status':'PASSED' if marker in text and 'kind=exited code='+exitcode in text and after==baseline else 'FAILED','compatibility_status':'FAILED' if name in {'code_actual_iframe','localpilot_actual_bundle'} else ('BLOCKED' if name=='web_capabilities' else 'PASSED'),'expected_marker':marker,'expected_exit':exitcode,'resources_after':after})
  if a.python_work:
   text=run(guest,'python3 /work/python_probe.py',timeout=240);(out/'python.log').write_text(text)
   report['python_observations']=[json.loads(line.split('COMPAT:',1)[1]) for line in text.splitlines() if line.startswith('COMPAT:')]
   report['checks'].append({'name':'python_observation_collection','harness_status':'PASSED' if 'COMPAT_DONE' in text and 'kind=exited code=0' in text and resources(guest)==baseline else 'FAILED'})
  report['resources_after']=resources(guest);report['status']='PASSED' if all(x['harness_status']=='PASSED' for x in report['checks']) else 'FAILED'
 except BaseException as e:report['error']=repr(e)
 finally:
  if guest:
   guest.close();shutil.copyfile(ROOT/f'build/{guest.name}_serial.log',out/'serial.log');shutil.copyfile(ROOT/f'build/{guest.name}_qemu.log',out/'qemu.log')
  report['disk_after_sha256']=sha(disk);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='python_stage'},indent=2));raise SystemExit(report['status']!='PASSED')
if __name__=='__main__':main()
