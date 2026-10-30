import argparse,contextlib,hashlib,json,os,re,shutil,subprocess,sys,traceback
from pathlib import Path

BASE=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-browser-net')
LOCAL=Path(__file__).resolve().parent
WORK=LOCAL/'qualified_regression_workspace'
SYSTEM=BASE/'build/network/qualified_system'
FIX=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-qt6-e17/build/qt_e17')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def worker(runner,rest):
    sys.path[:0]=[str(BASE/'tests'),str(BASE/'scripts')]
    import boot_smoke,work_disk,kernel_smoke,process_smoke,task_smoke,toolchain
    for module in [boot_smoke,work_disk,kernel_smoke,process_smoke,task_smoke,toolchain]:
        if hasattr(module,'ROOT'):module.ROOT=WORK
    source=runner.read_text()
    executed,count=re.subn(r'^ROOT\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[1\]',lambda _:"ROOT=Path("+repr(str(WORK))+")",source,count=1,flags=re.M)
    assert count==1,runner
    target=WORK/'build/executions'/runner.stem
    target.parent.mkdir(parents=True,exist_ok=True)
    target.with_suffix('.json').write_text(json.dumps({'runner':str(runner),'original_sha256':sha(runner),'executed_sha256':hashlib.sha256(executed.encode()).hexdigest(),'changed':'ROOT assignment only; all assertions and guest inputs unchanged'},indent=2)+'\n')
    sys.argv=[str(runner),*rest]
    if runner.name=='process_smoke.py':
        import tempfile
        from unittest.mock import patch
        from make_work_disk import create_fat32
        with tempfile.TemporaryDirectory(prefix='xos_e04_fixture_') as temporary:
            disk=Path(temporary)/'work.img';create_fat32(disk,512)
            original=boot_smoke.qemu_command
            def with_disk(*args,**kwargs):
                if kwargs.get('work_disk') is None:kwargs['work_disk']=disk
                return original(*args,**kwargs)
            target.with_name(target.name+'_fixture.json').write_text(json.dumps({'fixture_change':'Attach explicit disposable512MiBFAT32 workdisk; upstream E04 omitted disk and persistent-maintenance guard blocked commands. Assertions unchanged.'},indent=2)+'\n')
            with patch.object(boot_smoke,'qemu_command',with_disk):exec(compile(executed,str(runner),'exec'),{'__name__':'__main__','__file__':str(runner)})
    else:
        exec(compile(executed,str(runner),'exec'),{'__name__':'__main__','__file__':str(runner)})

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        return worker(Path(sys.argv[2]),sys.argv[3:])
    WORK.mkdir(exist_ok=False)
    for p in BASE.iterdir():
        if p.name not in ['build','.git']: (WORK/p.name).symlink_to(p,target_is_directory=p.is_dir())
    shutil.copytree(SYSTEM,WORK/'build')
    build=WORK/'build';out=build/'affected_regression';out.mkdir()
    manifest=json.loads((build/'manifest.json').read_text())
    for name,digest in manifest['sources'].items():assert sha(BASE/name)==digest,name
    for name,info in manifest['artifacts'].items():assert sha(build/name)==info['sha256'],name
    sdk=json.loads((FIX/'sdk/manifest.json').read_text())
    checked={}
    for name,digest in sdk['inputs'].items():
        if name.startswith('src/'):
            assert sha(BASE/name)==digest,name
            checked[name]=digest
    for name,digest in sdk['artifacts'].items():assert sha(FIX/'sdk'/name)==digest,name
    report={'status':'RUNNING','build_id':manifest['build_id'],'image_sha256':sha(build/'xos.img'),'sdk_source_reverification':checked,'tests':{}}
    sys.path[:0]=[str(BASE/'scripts'),str(BASE/'tests')]
    import build_threading_probes
    build_threading_probes.ROOT=WORK;build_threading_probes.BUILD=build;build_threading_probes.SDK=FIX/'sdk'
    saved_compiler_path=os.environ.get('COMPILER_PATH')
    with (out/'thread_probes_build.log').open('w') as log,contextlib.redirect_stdout(log):build_threading_probes.main()
    if saved_compiler_path is None:os.environ.pop('COMPILER_PATH',None)
    else:os.environ['COMPILER_PATH']=saved_compiler_path
    cases=[]
    for name,result in [('process_smoke','process_smoke_report.json'),('display_smoke','display_acceptance/report.json'),('threading_smoke','threading_report.json'),('threading_pthread_smoke','threading_pthread_report.json'),('threading_cpp_smoke','threading_cpp_report.json'),('file_smoke','file_smoke_report.json'),('persist_smoke','persist_smoke_report.json')]:
        cases.append((name,BASE/'tests'/(name+'.py'),[],build/result))
    for name,stem,marker,arg in [('core_smoke','core_smoke','QT_CORE_SMOKE_OK',''),('core_events','core_events','QT_EVENTS_OK',''),('core_quota','core_events','QT_THREAD_QUOTA_OK','quota'),('core_abi','core_abi','QT_ABI_OK',''),('core_memory','core_memory','QT_MEMORY_SAMPLE_OK',''),('core_lifecycle','core_lifecycle','QT_LIFECYCLE_OK','')]:
        r=out/(name+'.json');extras=['--image',str(build/'xos.img'),'--payload',str(FIX/'core_regressions'/(stem+'.elf')),'--report',str(r),'--marker',marker]
        if arg:extras+=['--argument',arg]
        cases.append((name,BASE/'tests/qt6_sdk_probe.py',extras,r))
    for name,runner,stem in [('core_fault','qt6_fault_probe.py','core_events'),('core_persist','qt6_persist_probe.py','core_extended'),('core_file_errors','qt6_file_errors.py','core_extended')]:
        r=out/(name+'.json');cases.append((name,BASE/'tests'/runner,['--image',str(build/'xos.img'),'--payload',str(FIX/'core_regressions'/(stem+'.elf')),'--report',str(r)],r))
    for case in ['pixels','interactive','lifecycle']:
        r=out/('gui_'+case);cases.append(('gui_'+case,BASE/'tests/qt6_gui_acceptance.py',['--image',str(build/'xos.img'),'--payload',str(FIX/'final_gui/qt_demo.elf'),'--output',str(r),'--case',case],r/'report.json'))
    for case in ['interactive','lifecycle']:
        r=out/('widgets_'+case);cases.append(('widgets_'+case,BASE/'tests/qt6_widgets_acceptance.py',['--image',str(build/'xos.img'),'--payload',str(FIX/'review_editor/notes.elf'),'--output',str(r),'--case',case],r/'report.json'))
    for name,runner,extra,result in cases:
        cmd=[sys.executable,str(Path(__file__).resolve()),'--worker',str(runner),*extra]
        with (out/(name+'.runner.log')).open('wb') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
        data=json.loads(result.read_text()) if result.exists() else {}
        report['tests'][name]={'status':'PASSED' if code==0 and data.get('status','').lower()=='passed' else 'FAILED','returncode':code,'command':cmd,'result':str(result),'error':data.get('error')}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(name,report['tests'][name]['status'],flush=True)
    report['status']='PASSED' if all(r['status']=='PASSED' for r in report['tests'].values()) else 'FAILED'
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    if report['status']!='PASSED':raise SystemExit(1)

if __name__=='__main__':main()
