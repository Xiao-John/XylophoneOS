# SPDX-License-Identifier: Apache-2.0
"""Compile real native dependency units; keep compilation separate from import."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--python-work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);work=a.python_work.resolve();sdk=a.sdk.resolve();native=ROOT/'build/modern_apps/python_deps/native-source'
 tools=out/'tools';tools.mkdir()
 for name in ['as','ld']:(tools/name).symlink_to(shutil.which('x86_64-elf-'+name))
 env=os.environ.copy();env['COMPILER_PATH']=str(tools);rows=[]
 for name,source,includes in [('psutil',native/'psutil-7.1.3/psutil/arch/posix/proc.c',[native/'psutil-7.1.3/psutil']),('Pillow',native/'pillow-11.3.0/src/_imaging.c',[native/'pillow-11.3.0/src/libImaging'])]:
  cmd=['x86_64-elf-gcc','-std=gnu11','-D__xos__=1','-DXOS_THREADED_RUNTIME','-mno-red-zone','-fno-pie','-fno-pic','-I'+str(work/'target_build'),'-I'+str(work/'source/Include'),'-isystem',str(sdk/'include'),*['-I'+str(x) for x in includes],*(['-DPILLOW_VERSION="11.3.0"'] if name=='Pillow' else []),'-c',str(source),'-o',str(out/(name+'.o'))]
  r=subprocess.run(cmd,env=env,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);rows.append({'name':name,'scope':'single unmodified translation unit with required build macros; not complete package link/import qualification','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'command':cmd,'returncode':r.returncode,'status':'PASSED' if r.returncode==0 else 'FAILED'})
 (out/'report.json').write_text(json.dumps(rows,indent=2)+'\n');print([(x['name'],x['status']) for x in rows])
if __name__=='__main__':main()
