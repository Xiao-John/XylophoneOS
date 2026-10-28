# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import json,hashlib,subprocess,sys
root=Path.cwd();out=root/'build/qt_e16/qualified_system_regressions';out.mkdir(exist_ok=False)
report={'status':'FAILED','image_sha256':hashlib.sha256((root/'build/xos.img').read_bytes()).hexdigest(),'tests':{}}
for name in ('threading_smoke','threading_pthread_smoke','threading_cpp_smoke','file_smoke','persist_smoke'):
 cmd=[sys.executable,str(root/'tests'/(name+'.py'))]
 with (out/(name+'.runner.log')).open('wb') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
 reportfile={'threading_smoke':'threading_report.json','threading_pthread_smoke':'threading_pthread_report.json','threading_cpp_smoke':'threading_cpp_report.json','file_smoke':'file_report.json','persist_smoke':'persist_report.json'}[name]
 src=root/'build'/reportfile
 if src.exists():(out/reportfile).write_bytes(src.read_bytes())
 # Guest runner's own raw serial and stderr are preserved under this snapshot.
 for s in (root/'build').glob('*_serial.log'):
  if s.is_file():(out/s.name).write_bytes(s.read_bytes())
 data=json.loads(src.read_text()) if src.exists() else {}
 report['tests'][name]={'status':'PASSED' if code==0 and data.get('status')=='passed' else 'FAILED','command':cmd,'checks':len(data.get('checks',[]))}
 print(name,report['tests'][name]['status'],flush=True)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
report['status']='PASSED' if all(v['status']=='PASSED' for v in report['tests'].values()) else 'FAILED'
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
