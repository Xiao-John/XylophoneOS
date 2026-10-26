# SPDX-License-Identifier: Apache-2.0
"""Collect version-bound source, original dependency inputs and correspondence evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
VERSION=(ROOT/'VERSION').read_text().strip()
OUT=ROOT/'build/releases'/VERSION

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def main():
    payload=OUT/'sources/payload'
    if payload.exists():raise SystemExit('source payload already exists; inspect instead of overwriting')
    payload.mkdir(parents=True)
    records=[]
    def copy(source,relative,expected=None,role='source'):
        source=Path(source);digest=sha(source)
        if expected and digest!=expected:raise ValueError('source input hash mismatch: '+str(source))
        target=payload/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        records.append({'path':relative,'sha256':digest,'bytes':target.stat().st_size,'role':role})
    old=ROOT/'build/releases/0.0.1-1024'
    old_release=json.loads((old/'release_manifest.json').read_text())
    if sha(ROOT/'build/cpp_bundle/seed_manifest.json')!=old_release['seed_manifest_sha256']:
        raise ValueError('GNU Seed changed; regenerate full matching overlays instead of reusing correspondence material')
    checks={name:digest for digest,name in [line.split(maxsplit=1) for line in (old/'public_CHECKSUMS.sha256').read_text().splitlines() if line.strip()]}
    for name in ('xos-0.0.1-1024-gnu-sources.tar.gz','xos-0.0.1-1024-gnu-source-supplement-gxx-lrealpath.tar.gz'):
        copy(old/'sources'/name,'unchanged_gnu_correspondence/'+name,checks[name],role='verbatim corresponding source for unchanged GNU Seed')
    for lock_name,filename,field in [('source_lock.json','Python-3.14.9.tar.xz','sha256'),('zlib_lock.json','zlib-1.3.2.tar.xz','sha256'),('idna_lock.json','idna-3.20-py3-none-any.whl','wheel_sha256')]:
        lock=json.loads((ROOT/'src/ports/cpython'/lock_name).read_text())
        folder='packages' if filename.endswith('.whl') else 'sources'
        copy(ROOT/'.cache/xos_seed/cpython'/folder/filename,'archives/'+filename,lock[field])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    # git archive contains only tracked project sources, never localpilot/cache/keychain.
    source_archive=payload/('xos-source-'+VERSION+'.tar.gz')
    subprocess.run(['git','archive','--format=tar.gz','--prefix=xylophoneos-'+VERSION+'/',
                    '--output='+str(source_archive),commit],cwd=ROOT,check=True)
    records.append({'path':source_archive.name,'sha256':sha(source_archive),'bytes':source_archive.stat().st_size,'role':'tracked XOS source snapshot','commit':commit})
    for path in [ROOT/'build/cpp_bundle/seed_manifest.json',ROOT/'build/cpp_bundle/sysroot_manifest.json',
                 ROOT/'.cache/xos_seed/gcc/relinks/target_runtime_v5_receipt/manifest.json',
                 ROOT/'.cache/xos_seed/cpython/2b6c1342ebe6fb8c22dc/py0a_report.json',
                 ROOT/'build/threading_sdk/manifest.json']:
        copy(path,'build_records/'+path.parent.name+'_'+path.name,role='build provenance')
    result={'version':VERSION,'source_commit':commit,'records':records,'notes':[
        'The unchanged GNU Seed retains its original 1024 source correspondence and supplemental overlays verbatim; it is not relabeled as newly rebuilt GNU source.',
        'Current XOS source includes CPython/dash/Make/newlib adaptation scripts and patches; CPython/zlib/idna original inputs are hash locked.',
        'This collection records material correspondence, not a complete legal or library-member audit.']}
    (payload/'source_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    output=OUT/'sources'/('xos-'+VERSION+'-sources.tar.gz')
    with tarfile.open(output,'w:gz',compresslevel=1) as tar:tar.add(payload,arcname='xos-'+VERSION+'-sources')
    (OUT/'source_manifest.json').write_text(json.dumps({**result,'archive_sha256':sha(output),'archive_bytes':output.stat().st_size},indent=2)+'\n')
    print(output,sha(output),output.stat().st_size)
if __name__=='__main__':main()
