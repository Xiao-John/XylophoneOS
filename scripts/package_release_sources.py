#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the locked GNU source archives and local XOS source overlays."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'build/releases/0.0.1-1024/sources'
PAYLOAD = DEST / 'payload'

def digest(path, algo='sha256'):
    h=hashlib.new(algo)
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def copy_file(src, dst, root_label, records, expected=None, algo='sha256'):
    src=Path(src)
    if not src.is_file(): raise FileNotFoundError(src)
    got=digest(src,algo)
    if expected and got.lower()!=expected.lower(): raise ValueError(f'hash mismatch {src}: {got} != {expected}')
    dst=Path(dst); dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
    records.append({'source':root_label,'path':str(src),'sha256':digest(dst),'size':dst.stat().st_size})
    return dst

def archive_members(archive):
    result={}
    with tarfile.open(archive,'r:*') as tf:
        for m in tf:
            p=PurePosixPath(m.name)
            if len(p.parts)<2 or p.parts[0].startswith('.'): continue
            rel=PurePosixPath(*p.parts[1:]).as_posix()
            if rel in ('','.'): continue
            if m.isfile():
                f=tf.extractfile(m); h=hashlib.sha256()
                while True:
                    b=f.read(1024*1024)
                    if not b: break
                    h.update(b)
                result[rel]=('file',h.hexdigest(),m.mode)
            elif m.issym(): result[rel]=('symlink',m.linkname,m.mode)
            elif m.isdir(): result[rel]=('dir','',m.mode)
    return result

def tree_members(tree):
    out={}
    for base,dirs,files in os.walk(tree,followlinks=False):
        dirs.sort(); files.sort(); bp=Path(base)
        for n in list(dirs):
            p=bp/n; rel=p.relative_to(tree).as_posix()
            if p.is_symlink(): out[rel]=('symlink',os.readlink(p),p.lstat().st_mode & 0o777); dirs.remove(n)
            else: out[rel]=('dir','',p.stat().st_mode & 0o777)
        for n in files:
            p=bp/n; rel=p.relative_to(tree).as_posix()
            if p.is_symlink(): out[rel]=('symlink',os.readlink(p),p.lstat().st_mode & 0o777)
            elif p.is_file(): out[rel]=('file',digest(p),p.stat().st_mode & 0o777)
    return out

def overlay(archive, tree, outdir, label, cache):
    key=str(archive)
    if key not in cache: cache[key]=archive_members(archive)
    upstream=cache[key]; local=tree_members(tree); changed=[]; deleted=[]
    for rel, meta in local.items():
        if upstream.get(rel)!=meta:
            changed.append(rel)
            src=Path(tree)/rel; dst=Path(outdir)/rel
            dst.parent.mkdir(parents=True,exist_ok=True)
            if src.is_symlink():
                dst.write_text('SYMLINK -> '+os.readlink(src)+'\n',encoding='utf-8')
            elif src.is_file(): shutil.copy2(src,dst)
    for rel in upstream.keys()-local.keys(): deleted.append(rel)
    return {'label':label,'source_tree':str(tree),'overlay_dir':str(Path(outdir).relative_to(PAYLOAD)),
      'changed_or_added':changed,'deleted':sorted(deleted),'changed_count':len(changed),'deleted_count':len(deleted)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',default=str(DEST)); a=ap.parse_args()
    dest=Path(a.output_dir).resolve()
    if dest!=DEST.resolve(): raise SystemExit('output directory is fixed to build/releases/0.0.1-1024/sources')
    if PAYLOAD.exists(): shutil.rmtree(PAYLOAD)
    PAYLOAD.mkdir(parents=True)
    records=[]
    gcc_lock=json.loads((ROOT/'src/ports/gcc/source_lock.json').read_text())
    bin_lock=json.loads((ROOT/'src/ports/binutils/source_lock.json').read_text())
    arc_specs=[
      (ROOT/'.cache/xos_seed/gcc/gcc-16.2.0.tar.xz','archives/gcc-16.2.0.tar.xz','sha256',gcc_lock['sha256']),
      (ROOT/'.cache/xos_seed/gcc/gmp-6.3.0.tar.bz2','archives/gmp-6.3.0.tar.bz2','sha512',gcc_lock['dependencies']['gmp']['sha512']),
      (ROOT/'.cache/xos_seed/gcc/mpfr-4.2.2.tar.bz2','archives/mpfr-4.2.2.tar.bz2','sha512',gcc_lock['dependencies']['mpfr']['sha512']),
      (ROOT/'.cache/xos_seed/gcc/mpc-1.3.1.tar.gz','archives/mpc-1.3.1.tar.gz','sha512',gcc_lock['dependencies']['mpc']['sha512']),
      (ROOT/'.cache/xos_seed/binutils/binutils-2.47.tar.xz','archives/binutils-2.47.tar.xz','sha256',bin_lock['sha256']),
      (Path('/tmp/newlib.tar.gz'),'archives/newlib-original.tar.gz','sha256',None),
    ]
    copied={}
    for src,rel,algo,expected in arc_specs:
        dst=copy_file(src,PAYLOAD/rel,str(src),records,expected,algo); copied[src.name]=dst
        records[-1]['verified_against_lock']=bool(expected); records[-1]['verification_algorithm']=algo
    ovs=[]
    upstream_cache={}
    for label,arc,tree in [
      ('gcc-c',copied['gcc-16.2.0.tar.xz'],ROOT/'.cache/xos_seed/gcc/source/gcc-16.2.0'),
      ('gcc-cpp',copied['gcc-16.2.0.tar.xz'],ROOT/'.cache/xos_seed/gcc/e08_5/gxx/source/gcc-16.2.0'),
      ('binutils',copied['binutils-2.47.tar.xz'],ROOT/'.cache/xos_seed/binutils/source/binutils-2.47')]:
        ovs.append(overlay(arc,tree,PAYLOAD/'overlays'/label,label,upstream_cache))
    # Port patches, headers, scripts, manifests, and notices (not caches or binaries).
    for sub in ['src/ports/gcc','src/ports/binutils']:
        for p in (ROOT/sub).rglob('*'):
            if not p.is_file() or '.git' in p.parts: continue
            if any(x in p.parts for x in ['build','source','install']): continue
            rel=p.relative_to(ROOT); copy_file(p,PAYLOAD/'materials'/rel, str(rel), records)
    for p in [ROOT/'src/third_party/newlib/COPYING.NEWLIB']:
        copy_file(p,PAYLOAD/'materials'/p.relative_to(ROOT),str(p.relative_to(ROOT)),records)
    # Actual build manifests and logs, including newlib build configuration.
    record_roots=[ROOT/'.cache/xos_seed/gcc/build',ROOT/'.cache/xos_seed/gcc/e08_5/gxx',ROOT/'.cache/xos_seed/gcc/e08_5/target_runtime',ROOT/'.cache/xos_seed/binutils/build',Path('/tmp/newlib-build')]
    for rr in record_roots:
        if not rr.exists(): continue
        for p in rr.rglob('*'):
            if not p.is_file() or p.suffix not in ('.log','.json') and p.name not in ('config.log',): continue
            if p.suffix=='.json' and p.name!='manifest.json': continue
            if any(x in p.parts for x in ('obj','lib','bin')): continue
            label='newlib-build' if str(rr).startswith('/tmp') else rr.relative_to(ROOT).as_posix()
            rel=Path(label)/p.relative_to(rr)
            copy_file(p,PAYLOAD/'materials/build_records'/rel,str(p),records)
    for p in [Path('/opt/homebrew/Cellar/x86_64-elf-gcc/16.2.0/.brew/x86_64-elf-gcc.rb'),Path('/opt/homebrew/Cellar/x86_64-elf-binutils/2.47/.brew/x86_64-elf-binutils.rb')]:
        if p.exists(): copy_file(p,PAYLOAD/'materials/host_toolchain'/p.name,str(p),records)
    try:
        cp=subprocess.run(['/opt/homebrew/bin/x86_64-elf-gcc','-v'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
        (PAYLOAD/'materials/host_toolchain').mkdir(parents=True,exist_ok=True)
        (PAYLOAD/'materials/host_toolchain/x86_64-elf-gcc-v.txt').write_text(cp.stdout,encoding='utf-8')
        records.append({'source':'command: /opt/homebrew/bin/x86_64-elf-gcc -v','path':'captured output','sha256':digest(PAYLOAD/'materials/host_toolchain/x86_64-elf-gcc-v.txt'),'size':(PAYLOAD/'materials/host_toolchain/x86_64-elf-gcc-v.txt').stat().st_size})
    except Exception as e: print('warning: unable to capture gcc -v:',e)
    manifest={'format':'xos-gnu-source-materials-v1','created_by':'scripts/package_release_sources.py','archives':records[:len(arc_specs)],'materials':records[len(arc_specs):], 'overlays':ovs,
      'notes':['Archive hashes are checked against repository source locks where available.','newlib archive has no pinned upstream hash in the repository; recorded SHA256 is observational only.','Overlay is a path/content/mode comparison against archive members; symlink overlays are represented by a marker file and must be restored as symlinks.','This is source correspondence material, not a per-member legal audit.']}
    (PAYLOAD/'source-materials-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (PAYLOAD/'README.txt').write_text('XOS GNU Seed corresponding source materials\n\nStart from archives/ and apply each overlay directory to the matching extracted source tree, deleting paths listed in source-materials-manifest.json. Original upstream archive bytes are preserved. For symlink entries represented in overlay files, recreate the link target recorded in the local source comparison procedure; inspect upstream and patch/config materials.\n\nThis collection does not certify per-member licensing or library-object provenance. See source-materials-manifest.json and the project licensing notes.\n',encoding='utf-8')
    tarout=dest/'xos-0.0.1-1024-gnu-sources.tar.gz'; tarout.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(tarout,'w:gz',compresslevel=1) as tf:
        tf.add(PAYLOAD,arcname='xos-0.0.1-1024-gnu-sources')
    print(json.dumps({'archive':str(tarout),'sha256':digest(tarout),'bytes':tarout.stat().st_size,'inputs':len(records),'overlays':{o['label']:o['changed_count'] for o in ovs}},indent=2))
if __name__=='__main__': main()
