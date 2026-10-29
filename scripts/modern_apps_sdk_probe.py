# SPDX-License-Identifier: Apache-2.0
"""Compile concrete required interfaces against a real XOS SDK, saving failures."""
import argparse,json,os,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--v8',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=a.sdk.resolve();v8=a.v8.resolve()
 tools=out/'tools';tools.mkdir()
 for name in ['as','ld']:(tools/name).symlink_to(shutil.which('x86_64-elf-'+name))
 env=os.environ.copy();env['COMPILER_PATH']=str(tools)
 flags=['-std=c++20','-nostdinc++','-isystem',str(sdk/'cpp/include'),'-isystem',str(sdk/'cpp/include/x86_64-elf'),'-isystem',str(sdk/'include'),'-I',str(v8)]
 rows=[]
 for source in sorted((ROOT/'tests/fixtures/modern_apps').glob('*.cc')):
  name=source.stem;cmd=['x86_64-elf-g++',*flags,'-c',str(source),'-o',str(out/(name+'.o'))];r=subprocess.run(cmd,env=env,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);rows.append({'name':name,'scope':'required-interface compilation preflight, not a full upstream build','status':'PASSED' if r.returncode==0 else 'FAILED','returncode':r.returncode,'command':cmd})
 (out/'report.json').write_text(json.dumps(rows,indent=2)+'\n');print([(r['name'],r['status']) for r in rows])
if __name__=='__main__':main()
