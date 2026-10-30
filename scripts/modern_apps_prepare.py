# SPDX-License-Identifier: Apache-2.0
"""Restore pinned public probe inputs, verify hashes and retain original notices."""
import base64,hashlib,json,re,tarfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def fetch(url,digest,path,encoded=False):
 if path.exists():
  if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('existing input changed: '+str(path))
  return
 data=urllib.request.urlopen(url,timeout=60).read()
 if encoded:data=base64.b64decode(data)
 if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('source hash mismatch: '+url)
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
def main():
 lock=json.loads((ROOT/'docs/reports/modern_apps_20261029/source_lock.json').read_text());out=ROOT/'build/modern_apps/sources'
 for row in lock['files']:
  if row['status']=='PASSED':fetch(row['url'],row['sha256'],out/row['path'],row['url'].endswith('format=TEXT'))
 q=lock['quickjs'];archive=out/q['archive'];fetch(q['url'],q['sha256'],archive)
 if not (out/'quickjs-2025-09-13').exists():
  with tarfile.open(archive) as t:t.extractall(out,filter='data')
 deps=ROOT/'build/modern_apps/python_deps'
 for row in json.loads((ROOT/'docs/reports/modern_apps_20261029/python_dependencies.json').read_text()):
  if row['status']!='PASSED':continue
  archive=deps/row['file'];fetch(row['url'],row['sha256'],archive)
  if archive.suffix=='.whl':
   with zipfile.ZipFile(archive) as z:
    if any(Path(x).is_absolute() or '..' in Path(x).parts for x in z.namelist()):raise ValueError('unsafe wheel')
    z.extractall(deps/'site-packages')
  else:
   with tarfile.open(archive) as t:t.extractall(deps/'native-source',filter='data')
 fixture=out/'vscode/src/vs/workbench/services/extensions/worker/webWorkerExtensionHostIframe.html'
 target=ROOT/'build/modern_apps/probes/code_extension_iframe.js';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(re.search(r'<script>(.*?)</script>',fixture.read_text(),re.S).group(1))
 print('Pinned public inputs restored; no runtime qualification implied')
if __name__=='__main__':main()
