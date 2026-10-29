from pathlib import Path
import subprocess,sys,json,shutil
root=Path.cwd();out=root/'build/qt_e17/review_system_regressions';out.mkdir(exist_ok=False)
report={'status':'FAILED','tests':{}}
for name,filename in [('threading_smoke','threading_report.json'),('threading_pthread_smoke','threading_pthread_report.json'),('threading_cpp_smoke','threading_cpp_report.json'),('file_smoke','file_smoke_report.json'),('persist_smoke','persist_smoke_report.json')]:
 with (out/(name+'.runner.log')).open('wb') as log: code=subprocess.run([sys.executable,root/'tests'/(name+'.py')],stdout=log,stderr=subprocess.STDOUT).returncode
 p=root/'build'/filename;data=json.loads(p.read_text()) if p.exists() else {}
 if p.exists():shutil.copyfile(p,out/filename)
 for s in (root/'build').glob('*_serial.log'):shutil.copyfile(s,out/s.name)
 report['tests'][name]={'status':'PASSED' if code==0 and data.get('status')=='passed' else 'FAILED','checks':len(data.get('checks',[]))}
 print(name,report['tests'][name],flush=True)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
report['status']='PASSED' if all(x['status']=='PASSED' for x in report['tests'].values()) else 'FAILED'
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
