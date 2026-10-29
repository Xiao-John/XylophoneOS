import subprocess,sys,json
from pathlib import Path
r=Path.cwd();b=r/'build/qt_e17';out=b/'review_core_regressions';out.mkdir(exist_ok=False)
for name in ('qmutex_contention','qinterrupt'):
 with (out/(name+'-build.log')).open('wb') as log:subprocess.run([sys.executable,r/'src/ports/qt6/build_fixture.py','--source',r/'docs/reports/qt_e15_qualified_20261028'/(name+'.cpp'),'--qrc',r/'tests/fixtures/qt6/resources.qrc','--sdk',b/'sdk','--qt-build',b/'widgets','--host-qt',r/'../XylophoneOS-qt6-e15/build/qt_e15/host-install','--binutils',r/'.cache/xos_seed/threading_sdk_tools','--output',out/(name+'.elf')],check=True,stdout=log,stderr=subprocess.STDOUT)
cases=[('smoke',b/'core_regressions/core_smoke.elf','QT_CORE_SMOKE_OK','','qt6_sdk_probe.py'),('events',b/'core_regressions/core_events.elf','QT_EVENTS_OK','','qt6_sdk_probe.py'),('quota',b/'core_regressions/core_events.elf','QT_THREAD_QUOTA_OK','quota','qt6_sdk_probe.py'),('fault',b/'core_regressions/core_events.elf','','','qt6_fault_probe.py'),('persist',b/'core_regressions/core_extended.elf','','','qt6_persist_probe.py'),('file_errors',b/'core_regressions/core_extended.elf','','','qt6_file_errors.py'),('abi',b/'core_regressions/core_abi.elf','QT_ABI_OK','','qt6_sdk_probe.py'),('memory',b/'core_regressions/core_memory.elf','QT_MEMORY_SAMPLE_OK','','qt6_sdk_probe.py'),('lifecycle',b/'core_regressions/core_lifecycle.elf','QT_LIFECYCLE_OK','','qt6_sdk_probe.py'),('wake',b/'final_wake/wake_gate_probe.elf','QT_WAKE_GATE_OK','','qt6_sdk_probe.py'),('mutex',out/'qmutex_contention.elf','QT_MUTEX_CONTENTION_OK','','qt6_sdk_probe.py'),('interrupt',out/'qinterrupt.elf','QT_INTERRUPT_ONLY_OK','','qt6_sdk_probe.py')]
report={'status':'FAILED','tests':{}}
for name,payload,marker,arg,runner in cases:
 cmd=[sys.executable,r/'tests'/runner,'--image',b/'review_system/xos.img','--payload',payload,'--report',out/(name+'.json')]
 if marker:cmd+=['--marker',marker]
 if arg:cmd+=['--argument',arg]
 with (out/(name+'.runner.log')).open('wb') as log:code=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
 p=out/(name+'.json');data=json.loads(p.read_text()) if p.exists() else {}
 report['tests'][name]={'status':'PASSED' if code==0 and data.get('status')=='PASSED' else 'FAILED','command':list(map(str,cmd)),'error':data.get('error')};print(name,report['tests'][name]['status'],flush=True);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
report['status']='PASSED' if all(x['status']=='PASSED' for x in report['tests'].values()) else 'FAILED';(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
