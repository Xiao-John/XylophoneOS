# SPDX-License-Identifier: Apache-2.0
"""Exact SDK/source identity for release inputs; a receipt is not an ABI qualification."""
import hashlib,json
from pathlib import Path

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def tree_receipt(root,exclude=()):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('expected real SDK directory')
    files={}
    directories=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('SDK symlink rejected: '+str(p))
        if p.is_file() and p.relative_to(root).as_posix() not in exclude:
            files[p.relative_to(root).as_posix()]=sha(p)
        elif p.is_dir():directories.append(p.relative_to(root).as_posix())
        elif not p.is_file():raise ValueError('SDK special file rejected: '+str(p))
    return {'tree_sha256':hashlib.sha256(canonical({'files':files,'directories':directories})).hexdigest(),'files':files,'directories':directories,'excluded_files':list(exclude)}

def verify_sdk(root,system):
    root=Path(root)
    expected={p[4:]:item['sha256'] for p,item in system['artifacts'].items() if p.startswith('sdk/')}
    required={'manifest.json','user.ld','crt0_posix.o','lib/libxos.a','lib/libxos_loader.a','lib/libc.a','lib/libm.a'}
    if not required<=expected.keys():raise ValueError('system manifest has no complete SDK input binding; rebuild it')
    receipt=tree_receipt(root)
    expected_directories=system.get('sdk_directories')
    if expected_directories is None:
        expected_directories=sorted({p.as_posix() for name in expected for p in Path(name).parents if p.as_posix()!='.'})
    if receipt['files']!=expected or receipt['directories']!=expected_directories:
        raise ValueError('SDK file set, directories or hash differs from frozen system artifacts')
    metadata=json.loads((root/'manifest.json').read_text())
    if metadata.get('build_id')!=system['build_id'] or metadata.get('abi')!=1 or metadata.get('target')!='x86_64-elf':
        raise ValueError('SDK build/ABI/target differs from frozen system')
    if metadata.get('configuration')!=system['configuration'] or metadata.get('runtime_model')!='single':
        raise ValueError('SDK configuration/runtime differs from frozen system')
    return {**receipt,'manifest_sha256':sha(root/'manifest.json'),'build_id':metadata['build_id'],
            'target':metadata['target'],'abi':metadata['abi'],
            'system_configuration_sha256':hashlib.sha256(canonical(system['configuration'])).hexdigest()}

def verify_runtime(root,lock):
    root=Path(root);receipt=tree_receipt(root)
    if receipt['tree_sha256']!=lock['tree_sha256'] or sha(root/'manifest.json')!=lock['manifest_sha256']:
        raise ValueError('C++ runtime differs from registered source snapshot')
    metadata=json.loads((root/'manifest.json').read_text())
    for item in metadata['archives']:
        if item['root']=='runtime' and sha(root/item['path'])!=item['sha256']:
            raise ValueError('runtime archive differs from provenance')
    return {**receipt,'manifest_sha256':sha(root/'manifest.json'),'scope':lock['scope']}

def verify_copied_inputs(root,sdk_input,runtime_input):
    root=Path(root)
    for name,digest in sdk_input['files'].items():
        if sha(root/name)!=digest:raise ValueError('copied SDK differs from validated input: '+name)
    for name,digest in runtime_input['files'].items():
        if name=='manifest.json':target=root/'target_runtime_provenance.json'
        elif name.startswith(('include/','lib/')):target=root/'cpp'/name
        else:continue
        if sha(target)!=digest:raise ValueError('copied runtime differs from validated input: '+name)


def verify_packaged_sdk(root,release):
    binding=release.get('sdk_binding')
    if not binding:raise ValueError('release has no SDK identity binding; legacy receipts remain historical')
    actual=tree_receipt(root,exclude=('release.json',))
    if actual!=binding['packaged']:raise ValueError('packaged SDK differs from release binding')
    return actual
