# SPDX-License-Identifier: Apache-2.0
"""Freeze actual receipts/logs and hashes without publishing private source or binaries."""
import argparse,gzip,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--guest',type=Path,required=True);p.add_argument('--system',type=Path,required=True);p.add_argument('--python-work',type=Path,required=True);a=p.parse_args();out=ROOT/'docs/reports/modern_apps_20261029';guest=a.guest.resolve();system=a.system.resolve();py=a.python_work.resolve();build=ROOT/'build/modern_apps'
 def copy(source,dest,compress=False):
  target=out/dest
  if compress:target=target.with_name(target.name+'.gz')
  target.parent.mkdir(parents=True,exist_ok=True)
  data=source.read_bytes()
  if compress:data=gzip.compress(data,mtime=0)
  if target.exists() and target.read_bytes()!=data:raise ValueError('refusing to rebind frozen evidence: '+str(target))
  target.write_bytes(data)
 for src,dst in [(guest/'report.json','guest/report.json'),(system/'license_report.json','inputs/license_report.json'),(build/'quickjs/receipt.json','build/js_receipt.json'),(build/'sdk-final/report.json','sdk/report.json'),(build/'native-final/report.json','native/report.json'),(build/'http-fixture-01/test.json','http_fixture/test.json'),(build/'http-fixture-01/fixture.json','http_fixture/fixture.json')]:copy(src,dst)
 for path in guest.glob('*.log'):copy(path,'guest/'+path.name,True)
 for path in (build/'sdk-final').glob('*.log'):copy(path,'sdk/'+path.name,True)
 for path in (build/'native-final').glob('*.log'):copy(path,'native/'+path.name,True)
 for src,dst in [(system/'manifest.json','inputs/system_manifest.json'),(system/'sdk/manifest.json','inputs/ordinary_sdk_manifest.json'),(build/'threading_sdk/manifest.json','inputs/threading_sdk_manifest.json'),(build/'threading_sdk_before_cpp_manifest.json','inputs/threading_sdk_before_cpp_manifest.json'),(py/'py0a_report.json','inputs/cpython_build_receipt.json'),(py/'stage_py1_manifest.json','inputs/cpython_stage_manifest.json'),(build/'http-fixture-01/requests.jsonl','http_fixture/requests.jsonl')]:copy(src,dst,True)
 for name in ['system-build.log','threading-sdk.log','threading-sdk-attempt2.log','sqlite-build-attempt1.log','sqlite-compile-attempt1.log','sqlite-build-attempt2.log','sqlite-build-attempt3.log','python-build.log','python-build-attempt2.log','js-build.log','js-build-attempt2.log','js-build-attempt3.log','js-build-stack64.log','js-build-rejection.log','localpilot-frontend-install.log','localpilot-frontend-build.log','localpilot-wheel.log','localpilot-wheel-attempt2.log','combined-guest-01.log','docs-reports.log']:
  path=build/name
  if path.exists():copy(path,'build/'+name,True)
 for name in ['js-guest-01','js-guest-02','combined-guest-02','combined-guest-03']:
  for path in (build/name).glob('*.log'):copy(path,'failures/'+name+'/'+path.name,True)
  path=build/name/'report.json'
  if path.exists():copy(path,'failures/'+name+'/report.json')
 for path in (build/'quickjs').glob('*receipt.json'):
  if path.name!='receipt.json':copy(path,'failures/quickjs/'+path.name)
 for path in (build/'quickjs').glob('*build.log'):copy(path,'failures/quickjs/'+path.name,True)
 artifacts=[system/'xos.img',system/'xos-install.iso',system/'kernel.elf',build/'quickjs/js_probe.elf',guest/'js_probe',py/'target_build/python.exe',py/'stage_py1/usr/bin/python3',guest/'work.img']
 artifacts.extend((build/'localpilot-wheel').glob('*.whl'))
 artifact_rows=[{'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path),'retention':'local; not a release asset'} for path in artifacts if path.is_file()]
 owned=list((ROOT/'scripts').glob('modern_apps_*.py'))+list((ROOT/'tests').glob('modern_apps_*.py'))+list((ROOT/'tests/fixtures/modern_apps').glob('*'))+list((ROOT/'licenses/modern_apps').glob('*'))+[ROOT/'licenses/components.json']
 sources={str(path.relative_to(ROOT)):sha(path) for path in owned if path.is_file()}
 g=json.loads((guest/'report.json').read_text());qemu=Path(g['qemu_command'][0]);artifact_rows.append({'path':str(qemu),'bytes':qemu.stat().st_size,'sha256':sha(qemu),'retention':'external existing test tool'})
 summary={'base_sha':'39083f9968d84b5679c86a74a6c8394033c0d915','system_build_id':json.loads((system/'manifest.json').read_text())['build_id'],'harness_status':g['status'],'harness_checks':len(g['checks']),'python_feature_counts':{s:sum(x['status']==s for x in g['python_observations']) for s in ['PASSED','FAILED']},'resources_before':g['resources_before'],'resources_after':g['resources_after'],'N2':'BLOCKED','full_chromium':'BLOCKED','full_chromium_build':'NOT_RUN','localpilot_core_api':'BLOCKED','localpilot_actual_guest_frontend':'FAILED','code_oss_actual_iframe_guest':'FAILED','full_code_oss':'BLOCKED','HTTPS':'NOT_RUN','artifacts':artifact_rows,'owned_probe_sources_sha256':sources,'note':'harness PASSED includes successful reproduction of compatibility failures; not product qualification'}
 copy_summary=out/'qualification.json'
 if copy_summary.exists():raise ValueError('qualification already frozen')
 copy_summary.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['artifacts','owned_probe_sources_sha256']},indent=2))
if __name__=='__main__':main()
