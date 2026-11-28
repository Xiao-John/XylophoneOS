# SPDX-License-Identifier: Apache-2.0
"""Build the independent guest xypm package against the selected XOS SDK."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from xos_app import build, init_project, pack
from xypm_format import DEFAULT_PROFILE,canonical,load_json,sha_file,require
ROOT=Path(__file__).resolve().parents[1]

def native_glibc_inputs():
    files = {
        'src/native_file_client.cpp': ROOT / 'src/user/sdk/file_client.cpp',
        'src/native_console.cpp': ROOT / 'src/user/sdk/text.cpp',
        'src/native_syscall.cpp': ROOT / 'src/user/arch/x86_64/syscall.cpp',
    }
    for scope, names in (('shared', ('abi_types', 'file_abi', 'process_abi', 'observation_abi', 'process_budget_abi')),
                         ('user', ('sdk', 'spawn', 'elf', 'file_client'))):
        for name in names:
            relative = f'xos/{name}.hpp'
            files['src/' + relative] = ROOT / 'src' / scope / 'include' / relative
    return files


def distribution_inputs(provisioning):
    files = {}
    for name in ('xypm_repository_auth.hpp', 'xypm_repository_auth.cpp',
                 'xypm_distribution.hpp', 'xypm_distribution.cpp',
                 'xypm_distribution_stage.hpp', 'xypm_distribution_stage.cpp',
                 'xypm_provisioning_client.hpp', 'xypm_provisioning_client.cpp'):
        files['src/' + name] = ROOT / 'src/user/programs' / name
    for name in ('identity', 'generation', 'elf'):
        files['src/dynamic_' + name + '.cpp'] = ROOT / 'src/user/loader/dynamic' / (name + '.cpp')
    files['src/native_elf.cpp'] = ROOT / 'src/user/loader/elf.cpp'
    for name in ('dynamic', 'dynamic_elf', 'fault_sha256', 'distribution_startup'):
        files['src/xos/' + name + '.hpp'] = ROOT / 'src/user/include/xos' / (name + '.hpp')
    for name in ('dynamic_abi', 'thread_abi'):
        files['src/xos/' + name + '.hpp'] = ROOT / 'src/shared/include/xos' / (name + '.hpp')
    files['src/xos/catalog_abi.hpp'] = provisioning / 'src/shared/include/xos/catalog_abi.hpp'
    for name in ('account_store.hpp', 'session_limits.hpp', 'service_core.hpp', 'daemon_protocol.hpp',
                 'provisioning_types.hpp', 'provisioning_store.hpp', 'snapshot_publication.hpp',
                 'provisioning_protocol.hpp', 'native_ipc.hpp', 'native_ipc_client.cpp',
                 'provisioning_client.cpp'):
        files['src/pumpkin/' + name] = provisioning / 'src/user/pumpkin' / name
    return files


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True)
    parser.add_argument('--profile',type=Path,default=DEFAULT_PROFILE)
    parser.add_argument('--fault-injection',action='store_true',help='build a test-only interruption fixture')
    parser.add_argument('--openssl-build',type=Path,help='verified target OpenSSL build output')
    parser.add_argument('--repository-trust',type=Path,help='independently provisioned Ed25519 bootstrap')
    parser.add_argument('--provisioning-source',type=Path,default=ROOT,
                        help='matching Pumpkin source with explicit publisher_checkpoint support')
    args=parser.parse_args()
    profile=load_json(args.profile)
    glibc = profile.get('runtime_family') == 'glibc'
    native = native_glibc_inputs() if glibc else {}
    authenticated = args.openssl_build is not None or args.repository_trust is not None
    extra = {}
    trust = None
    if authenticated:
        from xypm_release import trust_config, trust_header
        require(glibc and args.openssl_build is not None and args.repository_trust is not None,
                'authenticated distribution requires glibc, explicit OpenSSL build and bootstrap trust')
        trust = trust_config(load_json(args.repository_trust))
        require(trust['target_profile'] == profile['id'], 'bootstrap profile differs from xypm profile')
        crypto = load_json(args.openssl_build / 'report.json')
        require(crypto['status'] == 'static_sdk_and_probe_linked' and
                crypto['sdk_manifest_sha256'] == profile['sdk_binding']['sdk_manifest_sha256'] and
                crypto['sdk_binding']['sdk_tree_sha256'] == profile['sdk_binding']['sdk_tree_sha256'] and
                crypto['sdk_binding']['profile_sha256'] == hashlib.sha256(canonical(profile)).hexdigest(),
                'OpenSSL belongs to another SDK/profile')
        extra = distribution_inputs(args.provisioning_source.resolve(strict=True))
        for name, expected in crypto['installed'].items():
            if name.startswith('usr/include/openssl/'):
                original = args.openssl_build / 'prefix' / name
                require(sha_file(original) == expected, 'OpenSSL header differs from receipt: ' + name)
                extra['src/' + name.removeprefix('usr/include/')] = original
        for source_name, destination in (('usr/lib/libcrypto.a', 'src/vendor/libcrypto.a'),
                                          ('LICENSE.txt', 'src/vendor/OpenSSL_LICENSE.txt')):
            original = args.openssl_build / 'prefix' / source_name
            require(sha_file(original) == crypto['installed'][source_name], 'OpenSSL input differs from receipt')
            extra[destination] = original
        extra['src/vendor/openssl_build_receipt.json'] = args.openssl_build / 'report.json'
    source=ROOT/'src/user/programs/xypm.cpp'
    native_header=ROOT/'src/user/programs/xypm_native.hpp'
    journal_header=ROOT/'src/user/programs/xypm_journal.hpp'
    transaction_header=ROOT/'src/user/programs/xypm_transaction_impl.hpp'
    recovery_source=ROOT/'src/user/programs/xypm_recover.cpp'
    repository_headers=[ROOT/'src/user/programs'/name for name in ('xypm_repository.hpp','xypm_repository_io.hpp')]
    inputs = {'source':sha_file(source),'native_header':sha_file(native_header),'journal_header':sha_file(journal_header),'transaction_header':sha_file(transaction_header),'recovery_source':sha_file(recovery_source),'repository_headers':{path.name:sha_file(path) for path in repository_headers},'fault_injection':args.fault_injection,'text_header':sha_file(ROOT/'src/user/include/xos/text.hpp'),'width_data_header':sha_file(ROOT/'src/user/include/xos/unicode_width_data.hpp'),'build_script':sha_file(__file__),'builder':sha_file(ROOT/'scripts/xos_app.py'),'sdk_profile':profile}
    if glibc:
        inputs['glibc_native_sources'] = {name: sha_file(path) for name, path in native.items()}
    if authenticated:
        inputs['authenticated_distribution'] = {name:sha_file(path) for name,path in extra.items()}
        inputs['repository_bootstrap'] = trust
        inputs['openssl_receipt_sha256'] = sha_file(args.openssl_build / 'report.json')
        inputs['glibc_backend_sha256'] = sha_file(ROOT / 'scripts/build_glibc_program.py')
    key=hashlib.sha256(canonical(inputs)).hexdigest()[:20]
    folder=ROOT/'.cache/xos_seed/xypm'/key;folder.mkdir(parents=True,exist_ok=True)
    project=folder/'project'
    if not project.exists():
        init_project(project,'xos.xypm','cpp',profile)
        if args.fault_injection:(project/'src/main.cpp').write_bytes(b'#define XYP_TEST_FAULTS 1\n'+source.read_bytes())
        else:shutil.copyfile(source,project/'src/main.cpp')
        shutil.copyfile(native_header,project/'src/xypm_native.hpp')
        shutil.copyfile(journal_header,project/'src/xypm_journal.hpp')
        shutil.copyfile(transaction_header,project/'src/xypm_transaction_impl.hpp')
        for header in repository_headers:shutil.copyfile(header,project/'src'/header.name)
        (project/'src/xypm_recover.cpp').write_bytes(b'#define XYP_RECOVERY_LIBRARY 1\n'+recovery_source.read_bytes())
        (project/'src/xos').mkdir()
        shutil.copyfile(ROOT/'src/user/include/xos/text.hpp',project/'src/xos/text.hpp')
        shutil.copyfile(ROOT/'src/user/include/xos/unicode_width_data.hpp',project/'src/xos/unicode_width_data.hpp')
        feature_rows=''.join('    if (!__builtin_strcmp(name,'+json.dumps(name)+')) return true;\n' for name in profile['features'])
        profile_header=('// SPDX-License-Identifier: Apache-2.0\n#pragma once\n#include <cstring>\n'
                        '#define XYP_PACKAGE_PROFILE_ID '+json.dumps(profile['id'])+'\n'
                        'static inline bool xypm_profile_feature(const char* name) {\n'
                        +feature_rows+'    return false;\n}\n'
                        '#define XYP_PACKAGE_FEATURES(name) xypm_profile_feature(name)\n')
        if glibc:
            profile_header += '#define XYP_GLIBC_RUNTIME 1\n'
        if authenticated:
            profile_header += '#define XYP_AUTHENTICATED_DISTRIBUTION 1\n'
        (project/'src/xypm_profile.hpp').write_text(profile_header,encoding='utf-8')
        app=load_json(project/'xos_app.json')
        app['upstream_version']='0.5.0' if authenticated else '0.4.0'
        app['revision']=0
        app['sources'].append('src/xypm_recover.cpp')
        if 'stdio_transfer' in profile['features']:app['required_features'].append('stdio_transfer')
        app['files'].append({'source':'src/xos/unicode_width_data.hpp','path':'usr/share/xos.xypm/source/xos/unicode_width_data.hpp','role':'data'})
        app['files'].append({'source':'src/xos/text.hpp','path':'usr/share/xos.xypm/source/xos/text.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_native.hpp','path':'usr/share/xos.xypm/source/xypm_native.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_journal.hpp','path':'usr/share/xos.xypm/source/xypm_journal.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_transaction_impl.hpp','path':'usr/share/xos.xypm/source/xypm_transaction_impl.hpp','role':'data'})
        app['files'].append({'source':'src/xypm_recover.cpp','path':'usr/share/xos.xypm/source/xypm_recover.cpp','role':'data'})
        app['files'].append({'source':'src/xypm_profile.hpp','path':'usr/share/xos.xypm/source/xypm_profile.hpp','role':'data'})
        for header in repository_headers:
            app['files'].append({'source':'src/'+header.name,'path':'usr/share/xos.xypm/source/'+header.name,'role':'data'})
        for name, original in native.items():
            shutil.copyfile(original, project / name)
            if name.endswith('.cpp'):
                app['sources'].append(name)
            app['files'].append({'source': name, 'path': 'usr/share/xos.xypm/source/' + name[4:], 'role': 'data'})
        for name, original in extra.items():
            destination = project / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = original.read_bytes()
            if name.endswith('.cpp') and Path(name).name.startswith('xypm_'):
                prefix = b'#include "xypm_profile.hpp"\n'
                if args.fault_injection:
                    prefix += b'#define XYP_TEST_FAULTS 1\n'
                content = prefix + content
            destination.write_bytes(content)
            if name.endswith('.cpp'):
                app['sources'].append(name)
            # Archive bytes are captured by the project input receipt, while
            # the package carries the linked ELF and its exact archive receipt.
            if not name.endswith('.a'):
                app['files'].append({'source':name,'path':'usr/share/xos.xypm/source/'+name[4:],'role':'data'})
        if authenticated:
            (project/'src/xypm_repository_trust.hpp').write_text(trust_header(trust), encoding='utf-8')
            identity = bytes.fromhex(profile['sdk_binding']['sdk_manifest_sha256'])
            (project/'src/xypm_repository_sdk.hpp').write_text(
                '// SPDX-License-Identifier: Apache-2.0\n#pragma once\n#include <xos/abi_types.hpp>\n'
                'inline constexpr xos::u8 xypm_sdk_identity[32] = {' +
                ','.join(str(byte) for byte in identity) + '};\n', encoding='utf-8')
            for name in ('xypm_repository_trust.hpp', 'xypm_repository_sdk.hpp'):
                app['files'].append({'source':'src/'+name,'path':'usr/share/xos.xypm/source/'+name,'role':'data'})
            app['licenses'].append('usr/share/xos.xypm/source/vendor/OpenSSL_LICENSE.txt')
        (project/'xos_app.json').write_bytes(canonical(app))
    receipt=(build(project,args.sdk,profile,archives=('src/vendor/libcrypto.a',),gc_sections=True)
             if authenticated else build(project,args.sdk,profile))
    output=folder/'xypm.xpk'
    if output.exists():output.unlink()
    result=pack(project,args.sdk,profile,output)
    result['elf']=str(project/receipt['output']);result['cache_key']=key
    (folder/'manifest.json').write_bytes(canonical(result));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
