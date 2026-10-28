import importlib,json,os,sys,traceback
from pathlib import Path
root=Path.cwd();overlay=root/'build/qt_e15/recheck_20261028/regression_overlay'
sys.path[:0]=[str(root/'tests'),str(root/'scripts')]
import boot_smoke
boot_smoke.ROOT=overlay
results={}
for name in ['display_smoke','threading_smoke','threading_pthread_smoke','threading_cpp_smoke','file_smoke','persist_smoke']:
 module=importlib.import_module(name);module.ROOT=overlay
 sys.argv=[name]+(['--output',str(overlay/'build/g02')] if name=='display_smoke' else [])
 try:
  module.main();results[name]='PASSED'
 except BaseException:
  results[name]='FAILED';traceback.print_exc()
 print(name,results[name],flush=True)
(overlay.parent/'regressions.json').write_text(json.dumps(results,indent=2)+'\n')
raise SystemExit(0 if all(x=='PASSED' for x in results.values()) else 1)
