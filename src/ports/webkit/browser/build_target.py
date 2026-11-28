#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Link the actual WebCore renderer, bounded network broker and Qt viewport."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

PORT = Path(__file__).resolve().parent
ROOT = PORT.parents[3]
QT = ROOT / 'src/ports/qt6'
sys.path[:0] = [str(ROOT / 'scripts'), str(PORT.parent)]
from build_glibc_program import verify_elf
from glibc_g1_probe import clean_build_environment, tool_identity
from target_inputs import digest, recheck_inputs
from tls_policy import write_policy
from xypm_sdk_profile import metadata_snapshot, verify_profile


def recorded_files(directory, record, key, base=None):
    base = directory if base is None else base
    result = {}
    for name, expected in record[key].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() != name:
            raise ValueError('noncanonical artifact path: ' + name)
        path = base / relative
        if not path.is_file(): raise ValueError('missing artifact: ' + name)
        if path.is_symlink() and not path.resolve().is_relative_to(base):
            raise ValueError('artifact escapes its prefix: ' + name)
        result[path] = expected
    recheck_inputs(result)
    return result


def build(args):
    profile, profile_hash = metadata_snapshot(args.sdk_profile)
    binding = verify_profile(profile, 'glibc', args.sdk_build)
    sdk, sdk_hash = metadata_snapshot(args.sdk_build / 'manifest.json', profile['sdk_binding']['sdk_manifest_sha256'])
    if not {'cxx_runtime', 'threads', 'directories'} <= set(profile['features']):
        raise ValueError('browser requires a complete C++/pthread/Files SDK')
    page, page_hash = metadata_snapshot(args.page / 'build_record.json')
    qt, qt_hash = metadata_snapshot(args.qt / 'manifest.json')
    host, host_hash = metadata_snapshot(args.host_qt / 'manifest.json')
    ssl, ssl_hash = metadata_snapshot(args.openssl / 'report.json')
    if (page['status'] != 'webcore_local_page_linked' or qt['status'] != 'qtgui_viewport_installed' or
        host['status'] != 'qtbase_host_installed' or ssl['status'] != 'static_sdk_and_probe_linked' or
        any(item['sdk_manifest_sha256'] != sdk_hash for item in (page, qt, ssl)) or
        any(item['sdk_profile_sha256'] != profile_hash for item in (page, qt, ssl)) or
        qt['qtbase_archive_sha256'] != host['qtbase_archive_sha256']):
        raise ValueError('browser prerequisites differ from their bound SDK or are incomplete')
    inputs = {args.sdk_profile: profile_hash, args.sdk_build / 'manifest.json': sdk_hash,
              args.page / 'build_record.json': page_hash, args.qt / 'manifest.json': qt_hash,
              args.host_qt / 'manifest.json': host_hash, args.openssl / 'report.json': ssl_hash}
    inputs.update(recorded_files(args.qt, qt, 'artifacts', args.qt / 'prefix'))
    inputs.update(recorded_files(args.host_qt, host, 'artifacts', args.host_qt / 'prefix'))
    inputs.update(recorded_files(args.openssl, ssl, 'installed', args.openssl / 'prefix'))
    inputs.update({ROOT / name: value for name, value in page['inputs'].items()})
    inputs.update({ROOT / name: value for name, value in page['archives'].items()})
    inputs.update({ROOT / name: value for name, value in page.get('thin_members', {}).items()})
    inputs.update({args.page / name: value for name, value in page['objects'].items()})
    for directory in (PORT, ROOT / 'src/shared/include/xos', ROOT / 'src/user/include/xos',
                      QT / 'qpa', QT / 'runtime', ROOT / 'src/ports/browser_http',
                      ROOT / 'tests/fixtures/webkit/dom_css'):
        inputs.update({path: digest(path) for path in directory.rglob('*') if path.is_file() and path.suffix in
                       ('.cpp','.hpp','.h','.py','.txt','.cmake','.json','.html')})
    for path in (ROOT / 'tests/fixtures/webkit/dom_css.cpp', QT / 'glibc/glibc_toolchain.cmake',
                 QT / 'glibc/xos_qpa.cmake', QT / 'cmake/Platform/XOS.cmake', PORT.parent / 'icu/xos-compiler'):
        inputs[path] = digest(path)
    tools = {name: tool_identity('x86_64-elf-' + name) for name in ('gcc','g++','as','ld','ar','ranlib','strip')}
    for name, actual in tools.items():
        if not actual.get('available') or (name != 'strip' and actual['sha256'] != sdk['tools']['x86_64-elf-' + name]['sha256']):
            raise ValueError('target tool differs from SDK: ' + name)
    inputs[args.tls_root_der] = digest(args.tls_root_der)
    recheck_inputs(inputs)
    out = args.output; out.mkdir(parents=True, exist_ok=False)
    drivers = out / 'drivers'; (drivers / 'binutils').mkdir(parents=True)
    (drivers / 'cxx').symlink_to(PORT.parent / 'icu/xos-compiler')
    for name in ('as','ld'): (drivers / 'binutils' / name).symlink_to(tools[name]['path'])
    include_list = drivers / 'cxx-includes.txt'
    include_list.write_text('\n'.join(profile['sdk_binding']['cxx_runtime']['include_directories']) + '\n')
    policy_header = out / 'tls_policy.hpp'
    policy = write_policy(args.tls_origin,args.tls_address,args.tls_root_der,policy_header)
    inputs[policy_header] = digest(policy_header)
    env, removed = clean_build_environment(os.environ)
    env.update(LC_ALL='C', COMPILER_PATH=str(drivers / 'binutils'), XOS_ICU_SDK=str(args.sdk_build / 'sysroot'),
               XOS_ICU_CC=tools['gcc']['path'], XOS_ICU_CXX=tools['g++']['path'], XOS_ICU_CXX_INCLUDES=str(include_list))
    for name in ('CMAKE_PREFIX_PATH','Qt6_DIR','Qt6_ROOT','QT_ADDITIONAL_PACKAGES_PREFIX_PATH','QT_ADDITIONAL_HOST_PACKAGES_PREFIX_PATH'):
        env.pop(name, None)
    record = {'status':'building','sdk_manifest_sha256':sdk_hash,'sdk_profile_sha256':profile_hash,
              'sdk_binding':binding,'steps':[],'sanitized_environment':removed,'guest_qualification':'not_run'}
    if args.fault_navigation: record['test_profile'] = {'renderer_fault_navigation':args.fault_navigation}

    def save(): (out / 'build_record.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    def run(stage, command, cwd=ROOT):
        command = list(map(str,command)); log = out / (stage + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        record['steps'].append({'stage':stage,'command':command,'returncode':result.returncode,'log_sha256':digest(log)})
        save()
        if result.returncode: raise RuntimeError(stage + ' failed; see ' + str(log))
    save()
    try:
        commands = json.loads((args.page / 'cmake/compile_commands.json').read_bytes())
        reference = next(item for item in commands if 'WebCore.dir/' in item['command'])
        flags = next(step['command'] for step in page['steps'] if step['stage'] == 'compile-TestPage').copy()
        for option in ('-o','-c','-MF','-MT'):
            if option in flags:
                index=flags.index(option); del flags[index:index+2]
        flags = [item for item in flags if item != '-MD']
        # Preserve WebCore's generated configuration and genuine platform include set.
        flags += ['-I',str(PORT),'-I',str(ROOT/'src/user/include'),'-I',str(ROOT/'src/shared/include')]
        test_page = args.page / 'TestPage.o'
        page_object = out / 'page.o'
        run('page', [*flags,'-c',PORT/'page.cpp','-o',page_object],Path(reference['directory']))
        renderer_flags = ['-DXOS_CLARKE_TEST_FAULT_NAVIGATION=' + str(args.fault_navigation)] if args.fault_navigation else []
        common = [drivers/'cxx','-std=c++20','-O2','-g0','-ffunction-sections','-fdata-sections',
                  '-I',PORT,'-I',ROOT/'src/shared/include','-I',ROOT/'src/user/include']
        run('renderer', [*common,*renderer_flags,'-c',PORT/'renderer.cpp','-o',out/'renderer.o'])
        run('dom-css', [*common,'-c',ROOT/'tests/fixtures/webkit/dom_css.cpp','-o',out/'dom_css.o'])
        archives = [ROOT/name for name in page['archives']]
        for name in ('renderer','dom_css'):
            run('link-'+name,[drivers/'cxx','-Wl,--gc-sections,--no-keep-memory',out/(name+'.o'),page_object,test_page,
                '-Wl,--start-group',*archives,'-Wl,--end-group','-o',out/(name+'.elf')])
        network_objects=[]
        for name,path in (('network',PORT/'network.cpp'),('https',PORT/'https.cpp'),
                          ('http',ROOT/'src/ports/browser_http/http.cpp'),('transport',ROOT/'src/ports/browser_http/transport.cpp')):
            obj=out/(name+'.o'); network_objects.append(obj)
            run('compile-'+name,[*common,'-I',out,'-I',args.openssl/'prefix/usr/include','-c',path,'-o',obj])
        run('link-network',[drivers/'cxx','-Wl,--gc-sections,--no-keep-memory',*network_objects,
            '-Wl,--start-group',args.openssl/'prefix/usr/lib/libssl.a',args.openssl/'prefix/usr/lib/libcrypto.a',
            '-Wl,--end-group','-o',out/'network.elf'])
        prefix=args.qt/'prefix'; host_prefix=args.host_qt/'prefix'; packages=prefix/'lib/cmake'
        modules=('Core','Gui','BundledFreetype','BundledHarfbuzz','BundledPcre2','BundledZLIB')
        package_names=('Qt6',*('Qt6'+name for name in modules))
        configure=['cmake','-S',PORT,'-B',out/'qt','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
            '-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF','-DCMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY=OFF',
            '-DCMAKE_TOOLCHAIN_FILE='+str(packages/'Qt6/qt.toolchain.cmake'),
            '-DQT_CHAINLOAD_TOOLCHAIN_FILE='+str(QT/'glibc/glibc_toolchain.cmake'),
            '-DXOS_QT_PREFIX='+str(prefix),'-DQT_HOST_PATH='+str(host_prefix),'-DXOS_SOURCE_ROOT='+str(ROOT),
            '-DXOS_GLIBC_SDK='+str(args.sdk_build/'sysroot'),'-DXOS_GLIBC_TOOLS='+str(drivers/'binutils'),
            '-DXOS_GLIBC_CXX_INCLUDES='+';'.join(profile['sdk_binding']['cxx_runtime']['include_directories'])]
        configure += ['-DXOS_GLIBC_'+key+'='+tools[name]['path'] for key,name in
                      (('CC','gcc'),('CXX','g++'),('AR','ar'),('RANLIB','ranlib'))]
        configure += ['-D'+name+'_DIR:PATH='+str(packages/name) for name in package_names]
        run('qt-configure',configure)
        selected={name:Path(path).resolve() for name,path in
                  (line.split('=',1) for line in (out/'qt/qt_inputs.txt').read_text().splitlines())}
        expected={name:(prefix/('lib/libQt6'+name+'.a')).resolve() for name in modules}
        expected.update({name:(host_prefix/'libexec'/name).resolve() for name in ('moc','rcc')})
        if selected != expected: raise ValueError('viewport selected an unbound Qt archive or host generator')
        run('qt-build',['cmake','--build',out/'qt','--parallel',args.jobs])
        shutil.copyfile(out/'qt/viewport.elf',out/'viewport.elf')
        shutil.copyfile(prefix/'share/fonts/DejaVuSans.ttf',out/'DejaVuSans.ttf')
        headers={}
        for name in ('viewport','network','renderer','dom_css'):
            run('strip-'+name,[tools['strip']['path'],'--strip-debug',out/(name+'.elf')])
            headers[name]=verify_elf(out/(name+'.elf'))
        recheck_inputs(inputs)
        if verify_profile(profile,'glibc',args.sdk_build) != binding: raise ValueError('SDK changed during browser build')
        record.update(status='clarke_webcore_browser_linked',program_headers=headers,
            objects={path.name:digest(path) for path in out.glob('*.o')},
            artifacts={name:digest(out/name) for name in ('viewport.elf','network.elf','renderer.elf','dom_css.elf','DejaVuSans.ttf')},
            inputs={str(path.relative_to(ROOT)):value for path,value in inputs.items()},
            network_policy={'wire_version':2,'peer_policy_operation':21,'peer_policy_revision':1,
                'document_limit':65536,'navigation_timeout_ns':15000000000,'redirect_limit':0,
                'https':policy},
            feature_scope=['DOM','CSS box model','flex','grid','cascade','clipping','transforms','text','software RGBA paint'])
        save(); (out/'manifest.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    except BaseException as error:
        record.update(status='failed',error=str(error)); save(); raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-build','sdk-profile','page','qt','host-qt','openssl','tls-root-der','output'):
        parser.add_argument('--'+name,required=True,type=lambda value:Path(value).resolve())
    parser.add_argument('--tls-origin',required=True); parser.add_argument('--tls-address',required=True)
    parser.add_argument('--fault-navigation',type=int,default=0)
    parser.add_argument('--jobs',type=int,choices=(1,2),default=2)
    arguments=parser.parse_args()
    if arguments.fault_navigation < 0: parser.error('fault navigation must be a nonnegative diagnostic sequence')
    build(arguments)
