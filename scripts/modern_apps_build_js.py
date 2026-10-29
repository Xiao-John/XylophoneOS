# SPDX-License-Identifier: Apache-2.0
"""Cross-build the real QuickJS interpreter without a browser or OS shim."""
import argparse,hashlib,json,os,pathlib,shutil,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,required=True);p.add_argument('--sdk',type=pathlib.Path,required=True);p.add_argument('--cpp-runtime',type=pathlib.Path,required=True);a=p.parse_args()
 source=a.source.resolve();sdk=a.sdk.resolve();out=ROOT/'build/modern_apps/quickjs';out.mkdir(parents=True,exist_ok=True)
 tools=out/'tools';tools.mkdir(exist_ok=True)
 for name in ['as','ld']:
  target=tools/name
  if not target.exists():target.symlink_to(shutil.which('x86_64-elf-'+name))
 env=os.environ.copy();env['COMPILER_PATH']=str(tools)
 upstream=source
 patched=out/'source'
 if not patched.exists():
  shutil.copytree(source,patched)
  subprocess.run(['patch','-p1','-i',str(ROOT/'tests/fixtures/modern_apps/quickjs_xos.patch')],cwd=patched,check=True)
 source=patched
 sources=[source/x for x in ['quickjs.c','dtoa.c','libregexp.c','libunicode.c','cutils.c']]+[ROOT/'tests/fixtures/modern_apps/js_runner.c']
 common=['-O2','-g','-mno-red-zone','-fno-pic','-fno-pie','-fno-stack-protector','-ftls-model=local-exec','-D_GNU_SOURCE','-D__xos__=1','-DXOS_THREADED_RUNTIME','-DCONFIG_VERSION="2025-09-13"','-I'+str(source),'-I'+str(sdk/'include')]
 report={'status':'FAILED','upstream_modified':True,'patch_sha256':sha(ROOT/'tests/fixtures/modern_apps/quickjs_xos.patch'),'source_files':{str(x.relative_to(ROOT)):sha(x) for x in source.iterdir() if x.is_file()},'sdk_manifest_sha256':sha(sdk/'manifest.json'),'runtime_libraries':{str(x.resolve()):sha(x) for x in [a.cpp_runtime/'libsupc++.a',a.cpp_runtime/'libgcc.a']},'commands':[]}
 def run(cmd):
  report['commands'].append(cmd)
  with (out/'build.log').open('a') as log:r=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
  if r.returncode:raise RuntimeError('command failed: '+str(r.returncode))
 try:
  objects=[]
  for s in sources:
   obj=out/(s.stem+'.o');run(['x86_64-elf-gcc','-std=gnu11',*common,'-c',str(s),'-o',str(obj)]);objects.append(str(obj))
  elf=out/'js_probe.elf'
  run(['x86_64-elf-gcc','-nostdlib','-static','-no-pie','-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096','-T',str(sdk/'user.ld'),str(sdk/'crt0_posix.o'),*objects,'-Wl,--start-group','-Wl,--whole-archive',str(sdk/'lib/libxos.a'),'-Wl,--no-whole-archive','-L'+str(sdk/'lib'),'-lc','-lm',str(a.cpp_runtime.resolve()/'libsupc++.a'),str(a.cpp_runtime.resolve()/'libgcc.a'),'-Wl,--end-group','-o',str(elf)])
  report.update(status='PASSED',elf_sha256=sha(elf),elf_bytes=elf.stat().st_size)
 except Exception as e:report['error']=str(e)
 finally:(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(report['status']);raise SystemExit(report['status']!='PASSED')
if __name__=='__main__':main()
