# SPDX-License-Identifier: Apache-2.0
import hashlib,json,subprocess,sys
from pathlib import Path
root=Path.cwd();old=(root/'../XylophoneOS-qt6-e15').resolve();build=old/'build/qt_e15'
image=root/'build/qt_e16/qualified_system/xos.img';out=root/'build/qt_e16/qualified_regressions';out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
q=json.loads((root/'docs/reports/qt_e15_qualified_20261028/qualification.json').read_text())
for rel,h in json.loads((build/'frozen_sdk/manifest.json').read_text())['artifacts'].items():assert sha(build/'frozen_sdk'/rel)==h
for rel,h in json.loads((build/'frozen_sdk/manifest.json').read_text())['inputs'].items():assert sha(root/rel)==h
for stem,h in q['fixture_receipts'].items():
 r=build/(stem+'.receipt.json');assert sha(r)==h
 data=json.loads(r.read_text());assert sha(Path(data['source']))==data['source_sha256'];assert sha(build/(stem+'.elf'))==data['elf_sha256']
cases=[('smoke','final_core_smoke','QT_CORE_SMOKE_OK','','qt6_sdk_probe.py'),
 ('wake','final_wake_gate_v2','QT_WAKE_GATE_OK','','qt6_sdk_probe.py'),
 ('events','final_core_events_v2','QT_EVENTS_OK','','qt6_sdk_probe.py'),
 ('quota','final_core_events_v2','QT_THREAD_QUOTA_OK','quota','qt6_sdk_probe.py'),
 ('fault','final_core_events_v2','','','qt6_fault_probe.py'),
 ('persist','final_core_extended','','','qt6_persist_probe.py'),
 ('file-errors','final_core_extended','','','qt6_file_errors.py'),
 ('abi','final_core_abi','QT_ABI_OK','','qt6_sdk_probe.py'),
 ('memory','final_core_memory','QT_MEMORY_SAMPLE_OK','','qt6_sdk_probe.py'),
 ('mutex','qualified_mutex_contention','QT_MUTEX_CONTENTION_OK','','qt6_sdk_probe.py'),
 ('interrupt','qualified_interrupt','QT_INTERRUPT_ONLY_OK','','qt6_sdk_probe.py'),
 ('core-lifecycle','recheck_20261028/core_lifecycle_v2','QT_LIFECYCLE_OK','','qt6_sdk_probe.py')]
report={'status':'FAILED','image_sha256':sha(image),'tests':{},'driver_sha256':sha(Path(__file__))}
for name,stem,marker,arg,runner in cases:
 payload=build/(stem+'.elf');cmd=[sys.executable,str(root/'tests'/runner),'--image',str(image),'--payload',str(payload),'--report',str(out/(name+'.json'))]
 if marker:cmd+=['--marker',marker]
 if arg:cmd+=['--argument',arg]
 with (out/(name+'.runner.log')).open('wb') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
 data=json.loads((out/(name+'.json')).read_text()) if (out/(name+'.json')).exists() else {}
 report['tests'][name]={'status':'PASSED' if code==0 and data.get('status')=='PASSED' else 'FAILED','command':cmd,'payload_sha256':sha(payload),'runner_sha256':sha(root/'tests'/runner)}
 print(name,report['tests'][name]['status'],flush=True)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
report['status']='PASSED' if all(x['status']=='PASSED' for x in report['tests'].values()) else 'FAILED'
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
