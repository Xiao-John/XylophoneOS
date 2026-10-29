# SPDX-License-Identifier: Apache-2.0
"""Execute old assertions with explicit file-ISO input and isolated output paths."""
import argparse,difflib,hashlib,json,re,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--runner',type=Path,required=True);p.add_argument('--system-input',dest='system',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--g02-file-iso-only',action='store_true');a,rest=p.parse_known_args()
    work=a.workspace.resolve();assert ROOT/'build' in work.parents;work.mkdir(parents=True,exist_ok=False)
    for source in ROOT.iterdir():
        if source.name not in ['.git','build','.cache']:(work/source.name).symlink_to(source,target_is_directory=source.is_dir())
    shutil.copytree(a.system,work/'build')
    # Preserve actual host-side work images instead of allowing legacy fixtures'
    # TemporaryDirectory cleanup to remove final acceptance inputs/evidence.
    temporary_root=work/'build/temporary_inputs';temporary_root.mkdir()
    original_temporary=tempfile.TemporaryDirectory
    class retained_temporary(original_temporary):
        def __init__(self,*args,**kwargs):
            self._retained=kwargs.get('prefix') != 'xos_'
            if self._retained:kwargs['dir']=temporary_root
            super().__init__(*args,**kwargs)
        def cleanup(self):
            if self._retained:self._finalizer.detach()
            else:super().cleanup()
    tempfile.TemporaryDirectory=retained_temporary
    # Keep the exact previously frozen threading ELFs; this is a new kernel run,
    # not a relabeling of their old test results. Reverify each actual input.
    old=ROOT.parent/'XylophoneOS-network-abi/build/network_abi/qualified_regression_workspace/build'
    receipt=json.loads((old/'threading_probe_manifest.json').read_text())
    for name,digest in receipt['artifacts'].items():
        assert sha(old/name)==digest,name;shutil.copyfile(old/name,work/'build'/name)
    sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
    import boot_smoke,work_disk,kernel_smoke,process_smoke,task_smoke,toolchain
    for module in [boot_smoke,work_disk,kernel_smoke,process_smoke,task_smoke,toolchain]:
        if hasattr(module,'ROOT'):module.ROOT=work
    source=a.runner.read_text()
    executed,count=re.subn(r'ROOT\s*=\s*Path\(__file__\)\.resolve\(\)\.parents\[1\]',lambda _: 'ROOT=Path('+repr(str(work))+')',source,count=1)
    assert count==1,a.runner
    manifest=json.loads((a.system/'manifest.json').read_text())
    optical_input=not manifest['legacy_images_available']
    if optical_input:executed=executed.replace('xos.img','xos-install.iso')
    changes=['ROOT/output isolation', 'explicit supported file-ISO image and artifact key; optical boot' if optical_input else 'original floppy and ISO inputs preserved']
    if a.g02_file_iso_only:
        assert "for image in ('xos.iso','xos-install.iso'):" in executed
        executed=executed.replace("for image in ('xos.iso','xos-install.iso'):","for image in ('xos-install.iso',):")
        changes.append('G02 available-media subset: legacy inline ISO unavailable; NOT a full original 19-group media claim')
    # Old Qt ELFs were built from this exact SDK source tree, not from new FB17
    # diagnostics headers. Verify its original bytes; never rewrite old receipts.
    sdk_origin=ROOT.parent/'XylophoneOS-qt6-e17'
    if 'assert sha(ROOT/n)==h,n;checked[n]=h' in executed:
        executed=executed.replace('assert sha(ROOT/n)==h,n;checked[n]=h','assert sha(Path('+repr(str(sdk_origin))+')/n)==h,n;checked[n]=h')
        changes.append('verify old Qt SDK against its actual original source owner; new system separately hash-verified')
    if a.runner.name=='process_smoke.py':changes.append('existing formally repaired E04 fixture: disposable512MiBFAT32; no assertion changes')
    metadata={'original_runner':str(a.runner.resolve()),'original_sha256':sha(a.runner),'executed_sha256':hashlib.sha256(executed.encode()).hexdigest(),'adaptations':changes,'thread_inputs':receipt['artifacts'],'system_manifest_sha256':sha(a.system/'manifest.json')}
    (work/'build/adapter.json').write_text(json.dumps(metadata,indent=2)+'\n')
    (work/'build/executed_runner.py').write_text(executed)
    (work/'build/adapter.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True),executed.splitlines(True),fromfile='original',tofile='executed')))
    original=boot_smoke.qemu_command
    disk=None
    temporary=None
    if a.runner.name=='process_smoke.py':
        from make_work_disk import create_fat32
        temporary=tempfile.TemporaryDirectory(prefix='xos_e04_explicit_disk_');disk=Path(temporary.name)/'work.img';create_fat32(disk,512)
    def optical(*args,**kwargs):
        if optical_input:kwargs['iso']=True
        if disk is not None and kwargs.get('work_disk') is None:kwargs['work_disk']=disk
        return original(*args,**kwargs)
    boot_smoke.qemu_command=optical
    sys.argv=[str(a.runner),*rest]
    try:exec(compile(executed,str(a.runner),'exec'),{'__name__':'__main__','__file__':str(a.runner)})
    finally:
        if temporary:temporary.cleanup()
if __name__=='__main__':main()
