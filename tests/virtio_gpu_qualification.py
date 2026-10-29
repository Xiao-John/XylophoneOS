#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run independent VirtIO/VBE, fault, Qt and affected baseline regression gates."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
for n in ('system','quota-system','timeout-system','qt-fixtures','qt-runner-root','output'):p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);fixtures=a.qt_fixtures.resolve();qtroot=a.qt_runner_root.resolve();image=a.system.resolve()/'xos.img';sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads((a.system/'manifest.json').read_text())
for n,h in manifest['sources'].items():assert sha(ROOT/n)==h,n
assert sha(image)==manifest['artifacts']['xos.img']['sha256']
# These private aliases are for unchanged baseline tests. No other worktree build is used.
for source in a.system.resolve().iterdir():
 target=ROOT/'build'/source.name
 if target.is_symlink():
  assert 'virtio_gpu' in str(target.readlink()),target
  target.unlink();target.symlink_to(source,target_is_directory=source.is_dir())
 elif not target.exists():target.symlink_to(source,target_is_directory=source.is_dir())
report={'status':'FAILED','build_id':manifest['build_id'],'image_sha256':sha(image),'tests':{}}
def run(name,args,report_file):
 cmd=[sys.executable,*map(str,args)]
 with (out/(name+'.runner.log')).open('wb') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
 data=json.loads(report_file.read_text()) if report_file.exists() else {}
 report['tests'][name]={'status':'PASSED' if code==0 and data.get('status','').lower()=='passed' else 'FAILED','command':cmd,'report':str(report_file),'error':data.get('error')}
 print(name,report['tests'][name]['status'],flush=True);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
run('paired',[ROOT/'tests/virtio_gpu_acceptance.py','--system',a.system,'--qt-payload',fixtures/'final_gui/qt_demo.elf','--access-payload',ROOT/'build/virtio_gpu/access_fault.elf','--output',out/'paired'],out/'paired/report.json')
run('fault_profiles',[ROOT/'tests/virtio_gpu_fault_profiles.py','--default-system',a.system,'--quota-system',a.quota_system,'--timeout-system',a.timeout_system,'--qt-payload',fixtures/'final_gui/qt_demo.elf','--output',out/'fault_profiles'],out/'fault_profiles/report.json')
qt_cases=[('notes_interactive',qtroot/'tests/qt6_widgets_acceptance.py',fixtures/'review_editor/notes.elf',['--case','interactive'],'output'),('notes_lifecycle',qtroot/'tests/qt6_widgets_acceptance.py',fixtures/'review_editor/notes.elf',['--case','lifecycle'],'output'),('gui_input',ROOT/'tests/qt6_gui_acceptance.py',fixtures/'final_gui/qt_demo.elf',['--case','interactive'],'output'),('gui_lifecycle',ROOT/'tests/qt6_gui_acceptance.py',fixtures/'final_gui/qt_demo.elf',['--case','lifecycle'],'output')]
for name,stem,marker,arg,runner in [('core_smoke','core_smoke','QT_CORE_SMOKE_OK','','qt6_sdk_probe.py'),('core_events','core_events','QT_EVENTS_OK','','qt6_sdk_probe.py'),('core_quota','core_events','QT_THREAD_QUOTA_OK','quota','qt6_sdk_probe.py'),('core_fault','core_events','','','qt6_fault_probe.py'),('core_persist','core_extended','','','qt6_persist_probe.py'),('core_file_errors','core_extended','','','qt6_file_errors.py'),('core_abi','core_abi','QT_ABI_OK','','qt6_sdk_probe.py'),('core_memory','core_memory','QT_MEMORY_SAMPLE_OK','','qt6_sdk_probe.py'),('core_lifecycle','core_lifecycle','QT_LIFECYCLE_OK','','qt6_sdk_probe.py')]:
 extra=['--marker',marker] if marker else []
 if arg:extra+=['--argument',arg]
 qt_cases.append((name,ROOT/'tests'/runner,fixtures/'core_regressions'/(stem+'.elf'),extra,'report'))
for name,runner,payload,extra,kind in qt_cases:
 target=out/name if kind=='output' else out/(name+'.json');args=[ROOT/'tests/virtio_gpu_run_qt.py','--runner',runner,'--backend','virtio','--image',image,'--payload',payload,'--'+kind,target,*extra]
 run(name,args,target/'report.json' if kind=='output' else target)
run('g02_vbe',[ROOT/'tests/display_smoke.py','--output',out/'g02_vbe'],out/'g02_vbe/report.json')
# Build pthread probes from the already hash-verified, compatible current SDK.
sys.path.insert(0,str(ROOT/'scripts'));import build_threading_probes
build_threading_probes.SDK=fixtures/'sdk'
with (out/'thread_probes_build.log').open('w') as log:
 import contextlib
 with contextlib.redirect_stdout(log):build_threading_probes.main()
for name,filename in [('threading_smoke','threading_report.json'),('threading_pthread_smoke','threading_pthread_report.json'),('threading_cpp_smoke','threading_cpp_report.json'),('file_smoke','file_smoke_report.json'),('persist_smoke','persist_smoke_report.json')]:
 run(name,[ROOT/'tests'/(name+'.py')],ROOT/'build'/filename)
 if (ROOT/'build'/filename).exists():shutil.copyfile(ROOT/'build'/filename,out/filename)
 dest=out/name;dest.mkdir(exist_ok=True)
 for source in (ROOT/'build').glob('*_serial.log'):shutil.copyfile(source,dest/source.name)
report['status']='PASSED' if all(x['status']=='PASSED' for x in report['tests'].values()) else 'FAILED';(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
if report['status']!='PASSED':raise SystemExit(1)
