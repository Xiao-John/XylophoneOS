# SPDX-License-Identifier: Apache-2.0
"""Read a private LocalPilot checkout; publish metadata, never its source text."""
import argparse,ast,hashlib,json,subprocess,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();source=a.source.resolve();rows=[];files={}
 for folder in ['agent','computer','localpilot_api','localpilot_service','localpilot_plugins','localpilot_channels','companion','suite']:
  for file in sorted((source/folder).rglob('*.py')):
   if any(x in {'build','dist','__pycache__'} for x in file.parts):continue
   relative=file.relative_to(source).as_posix();files[relative]=sha(file)
   try:tree=ast.parse(file.read_text())
   except SyntaxError as e:rows.append({'path':relative,'parse_error':str(e)});continue
   for node in ast.walk(tree):
    if isinstance(node,ast.Import):names=[x.name for x in node.names]
    elif isinstance(node,ast.ImportFrom):names=[node.module or '']
    else:continue
    rows.append({'path':relative,'line':node.lineno,'imports':names})
 manifests={p:sha(source/p) for p in ['pyproject.toml','requirements.txt','suite/pyproject.toml','companion/pyproject.toml','desktop/package.json','desktop/package-lock.json','desktop/src-tauri/Cargo.toml','desktop/src-tauri/Cargo.lock'] if (source/p).exists()}
 core=tomllib.loads((source/'pyproject.toml').read_text())['project'];suite=tomllib.loads((source/'suite/pyproject.toml').read_text())['project'];comp=tomllib.loads((source/'companion/pyproject.toml').read_text())['project']
 report={'source_sha':subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),'tracked_diff':subprocess.check_output(['git','-C',str(source),'diff','--stat'],text=True),'source_is_private':True,'source_text_exported':False,'versions':{'core':core['version'],'suite':suite['version'],'companion':comp['version']},'dependencies':{'core':core['dependencies'],'suite':suite['dependencies'],'companion':comp['dependencies']},'manifest_sha256':manifests,'python_files_sha256':files,'imports':rows,'frontend_outputs':{str(x.relative_to(source/'desktop/dist')):{'sha256':sha(x),'bytes':x.stat().st_size} for x in (source/'desktop/dist').rglob('*') if x.is_file()}}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print('Audited',len(files),'Python files; copied no private source text')
if __name__=='__main__':main()
