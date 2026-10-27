# SPDX-License-Identifier: Apache-2.0
"""Deterministic errors in real files.cpp recovery; host FatFs, no guest/fault hardware claim."""
import hashlib,json,subprocess,sys,tempfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from make_work_disk import make_image

def main():
    out=ROOT/'build/audit_01/recovery';out.mkdir(parents=True,exist_ok=True)
    source=ROOT/'tests/fixtures/recovery/recovery_faults.cpp'
    command=[shutil.which('clang++') or 'c++','-std=c++17','-O1','-w',
             '-I'+str(ROOT/'src/third_party/fatfs'),'-I'+str(ROOT/'src/user/include'),'-I'+str(ROOT/'src/shared/include'),
             str(source),str(ROOT/'src/third_party/fatfs/ff.c'),str(ROOT/'src/user/services/fatfs_unicode.cpp'),'-o',str(out/'recovery_faults')]
    subprocess.run(command,check=True)
    with tempfile.TemporaryDirectory(prefix='xos_recovery_') as temp:
        image=Path(temp)/'private.img';image.write_bytes(make_image())
        run=subprocess.run([str(out/'recovery_faults'),str(image)],check=True,capture_output=True,text=True)
    paths=['src/user/services/files.cpp','tests/fixtures/recovery/recovery_faults.cpp','src/third_party/fatfs/ff.c']
    report={'status':'passed','scope':'production recovery with real host FatFs and API-boundary injected errors',
            'guest':'not_run_by_this_runner','output':run.stdout,'command':command,
            'sources':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(run.stdout,end='')
if __name__=='__main__':main()
