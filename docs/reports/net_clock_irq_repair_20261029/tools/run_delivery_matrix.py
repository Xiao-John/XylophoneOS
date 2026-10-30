import concurrent.futures,hashlib,json,os,subprocess,sys
from pathlib import Path
R=Path.cwd();B=R/'build/clock_irq';S=B/'delivery_default';D=B/'delivery_diagnostic';OLD=R.parent/'XylophoneOS-browser-net';FIX=R.parent/'XylophoneOS-qt6-e17/build/qt_e17';AD=R/'tests/clock_irq_adapter.py'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest=json.loads((S/'manifest.json').read_text())
for n,h in manifest['sources'].items():assert sha(R/n)==h,n
jobs=[]
def job(name,runner,system,extra,expected_report,**kw):
 w=B/'delivery_runs'/name
 cmd=[sys.executable,str(AD),'--runner',str(runner),'--system-input',str(system),'--workspace',str(w),*kw.get('adapter',[]),*map(str,extra)]
 jobs.append({'name':name,'command':cmd,'report':str(expected_report),'runner_sha256':sha(runner),'scope':kw.get('scope','full original behavioral assertions on explicit file-ISO'),'expected_failure':kw.get('expected_failure',False)})
old_report=json.loads((OLD/'docs/reports/virtio_net_n1_20261029/regressions/affected_regression/report.json').read_text())
old_work='/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-network-abi/build/network_abi/qualified_regression_workspace'
for name,row in old_report['tests'].items():
 w=B/'delivery_runs'/name;extra=[str(x).replace(old_work,str(w)) for x in row['command'][4:]]
 result=Path(row['result'].replace(old_work,str(w)))
 job(name,Path(row['command'][3]),S,extra,result,scope='original assertions and original supported floppy/ISO inputs')
ACCESS=R.parent/'XylophoneOS-network-abi/build/network_abi/access_fault.elf'
for name,mode,gpu,access in [('n1_echo','echo',False,False),('n1_timeout','timeout',False,False),('n1_overflow','overflow',False,False),('n1_jumbo','jumbo',False,False),('n1_absent','absent',False,False),('n1_echo_gpu','echo',True,False),('n1_isolation','echo',False,True),('n1_quota','quota',False,False)]:
 w=B/'delivery_runs'/name;system=B/'delivery_net_quota' if mode=='quota' else D
 extra=['--system',system,'--output',w/'build/results','--mode',mode]
 if gpu:extra+=['--gpu']
 if access:extra+=['--access-payload',ACCESS]
 job(name,OLD/'tests/virtio_net_acceptance.py',system,extra,w/'build/results/report.json')
runner=OLD/'docs/reports/virtio_net_n1_20261029/gates/jumbo_qt/executed_runner.py';w=B/'delivery_runs/n1_jumbo_qt'
job('n1_jumbo_qt',runner,D,['--system',D,'--output',w/'build/results','--mode','jumbo','--access-payload',ACCESS],w/'build/results/report.json')
# Input/path-only transformation for the frozen quota runner's old parents[4] source location.
inputs=B/'inputs';inputs.mkdir(exist_ok=True);original=OLD/'docs/reports/virtio_net_n1_20261029/probes/quota_reclamation.py';data=original.read_text().replace('parents[4]','parents[1]').replace('build/network/qualified_quota/','build/');qr=inputs/'quota_reclamation.py';qr.write_text(data)
(inputs/'quota_adapter.json').write_text(json.dumps({'original':str(original),'sha256':sha(original),'executed_sha256':sha(qr),'changes':['ROOT source location','explicit system input directory; assertions unchanged']},indent=2)+'\n');w=B/'delivery_runs/n1_quota_reclaim'
job('n1_quota_reclaim',qr,B/'delivery_net_quota',[],w/'build/network/qualified_gates/quota_reclaim/report.json')
w=B/'delivery_runs/gpu_paired'
job('gpu_paired',OLD/'tests/virtio_gpu_acceptance.py',S,['--system',S,'--qt-payload',FIX/'final_gui/qt_demo.elf','--access-payload',ACCESS,'--output',w/'build/results'],w/'build/results/report.json')
w=B/'delivery_runs/gpu_failures'
job('gpu_failures',OLD/'tests/virtio_gpu_fault_profiles.py',S,['--default-system',S,'--quota-system',B/'delivery_gpu_quota','--timeout-system',B/'delivery_gpu_timeout','--qt-payload',FIX/'final_gui/qt_demo.elf','--output',w/'build/results'],w/'build/results/report.json')
# Real browser B1 remains offline; reuse original pages and ELF without editing its worktree.
A=R.parent/'XylophoneOS-aurora-browser'
for case in ['interactive','negative','lifecycle']:
 name='browser_'+case;w=B/'delivery_runs'/name
 job(name,B/'inputs/aurora_browser_acceptance.py',S,['--image',S/'xos.img','--payload',A/'build/browser/target/aurora.elf','--output',w/'build/results','--case',case],w/'build/results/report.json')
# Keep original browser sources visible in each isolated root; these are immutable fixture symlinks only.
for j in jobs:
 if j['name'].startswith('browser_'):j['pre_fixture']='browser_pages'
(B/'delivery_matrix_inputs.json').write_text(json.dumps({'system_manifest_sha256':sha(S/'manifest.json'),'jobs':jobs},indent=2)+'\n')
env=os.environ.copy();env['QEMU']=str(R.parent/'runtime/qemu-prefix/Cellar/qemu/11.1.2/bin/qemu-system-x86_64');env['PYTHONDONTWRITEBYTECODE']='1'
results={}
def run(j):
 log=B/('delivery_'+j['name']+'.runner.log')
 with log.open('wb') as f:code=subprocess.run(j['command'],env=env,stdout=f,stderr=subprocess.STDOUT).returncode
 p=Path(j['report']);data=json.loads(p.read_text()) if p.exists() else {}
 return j['name'],{'status':'PASSED' if code==0 and data.get('status','').lower()=='passed' else 'FAILED','returncode':code,'report':j['report'],'error':data.get('error'),'expected_failure':j['expected_failure'],'scope':j['scope']}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for future in concurrent.futures.as_completed([pool.submit(run,j) for j in jobs]):
  name,result=future.result();results[name]=result;print(name,result['status'],str(result['error'])[:160],flush=True);(B/'delivery_matrix_results.json').write_text(json.dumps(results,indent=2)+'\n')
