import json
from pathlib import Path
import re
import subprocess

from xos_app import tree_receipt
from xypm_format import PackageError, canonical, load_json, sha_file, verify_package
from xypm_sdk_profile import verify_profile

ROOT = Path('build/unified').resolve()
kits = {
    'unified': ROOT/'relocated/application-sdk',
    'stock': ROOT/'rollback/stock',
    'browser': ROOT/'rollback/browser',
}
macro_names = ('_GLIBCXX_USE_CXX11_ABI', '_GLIBCXX_USE_DUAL_ABI', '_GLIBCXX_INLINE_VERSION',
               '_GLIBCXX_HAS_GTHREADS')
archives = ('libc.a', 'libm.a', 'libgcc.a', 'libstdc++.a', 'libsupc++.a')
profiles = {name: load_json(kit/'profile.json') for name,kit in kits.items()}

def macro_defs(kit):
    path = kit/'sdk/sysroot/usr/include/c++/16.2.0/x86_64-unknown-xos/bits/c++config.h'
    return {name: value.strip() for name,value in
            re.findall(r'^[ \t]*#[ \t]*define[ \t]+(_GLIBCXX_[A-Z0-9_]+)[ \t]+([^\n]+)$',
                       path.read_text(), re.M)}

def names(archive):
    dump = subprocess.check_output(['x86_64-elf-nm','--defined-only','--extern-only',str(archive)],text=True)
    return set(name for name in re.findall(r'^[a-f0-9]+ [A-Za-z?] (\S+)$',dump,re.M))

def rejected(function, *args):
    try:
        function(*args)
    except PackageError as error:
        return str(error)
    raise AssertionError('cross-profile pairing unexpectedly accepted')

metadata = {'profiles': {}, 'cross_rejections': {}, 'symbols': {}, 'compiler_tools': {}}
for name,kit in kits.items():
    macro = macro_defs(kit)
    metadata['profiles'][name] = {
        'binding': verify_profile(profiles[name], 'glibc', kit/'sdk'),
        'sdk_manifest_sha256': sha_file(kit/'sdk/manifest.json'),
        'public_abi_macros': {name: macro[name] for name in macro_names},
        'realpath_enabled': macro.get('_GLIBCXX_USE_REALPATH'),
    }
for name in ('stock','browser'):
    assert metadata['profiles']['unified']['public_abi_macros'] == metadata['profiles'][name]['public_abi_macros']
    metadata['cross_rejections'][name] = {
        'previous_profile_current_kit': rejected(verify_profile, profiles[name], 'glibc', kits['unified']/'sdk'),
        'current_profile_previous_kit': rejected(verify_profile, profiles['unified'], 'glibc', kits[name]/'sdk'),
        'new_xpk_previous_profile': rejected(verify_package, ROOT/'consumer/cxx.xpk', profiles[name]),
    }
assert metadata['profiles']['unified']['realpath_enabled'] == '1'

for library in archives:
    definitions = {key: names(root/'sdk/sysroot/usr/lib'/library) for key,root in kits.items()}
    assert definitions['unified']
    metadata['symbols'][library] = {'counts': {key: len(values) for key,values in definitions.items()}}
    if library == 'libc.a':
        expected = {'faccessat','__faccessat','readlink','realpath','pthread_create','pthread_getattr_np'}
        assert expected <= definitions['unified']
        metadata['symbols'][library]['selected_present'] = sorted(expected)
    for key in ('stock','browser'):
        removed = definitions[key] - definitions['unified']
        added = definitions['unified'] - definitions[key]
        metadata['symbols'][library][key] = {'missing_from_unified': sorted(removed),
                                              'new_in_unified': sorted(added)}
metadata['compiler_tools'] = dict(line.split() for line in (ROOT/'records/cxx-tools.txt').read_text().splitlines())
c = load_json(ROOT/'sdk_c/manifest.json')
for name,digest in metadata['compiler_tools'].items():
    assert c['tools']['x86_64-elf-'+name]['sha256'] == digest

archive = ROOT/'xos-glibc-unified-cxx-sdk.tar.gz'
kit_sha = tree_receipt(kits['unified'])[0]
assert kit_sha == tree_receipt(ROOT/'application-sdk')[0] == load_json(ROOT/'records/packaging.json')['kit_tree_sha256']
metadata['relocated_kit'] = {'archive_bytes': archive.stat().st_size, 'archive_sha256': sha_file(archive),
                            'kit_tree_sha256': kit_sha, 'original_and_relocated_equal': True}
(ROOT/'records/host-abi.json').write_bytes(canonical(metadata))
