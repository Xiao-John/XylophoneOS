# SPDX-License-Identifier: Apache-2.0
"""Real XOS C3 here-documents and sbase Make, including guest self-build."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
from boot_smoke import Guest
from dash_b2_smoke import build_probe
from process_smoke import command, resources
from released_test_disk import prepare_release_disk, ensure_directory
from task_smoke import send_bytes, pump
from work_disk import transfer, host_tool

FIXTURES = ROOT/'tests/fixtures/dash_c3'
LARGE = ''.join(chr(65+i%26) for i in range(65572))+'\n'
HERE_CASES = {
    'quoted': "v=EXPANDED; \"$PROBE\" copy <<'DOC'\n$v $((2+3)) $(printf hidden) `printf hidden` \\literal\nDOC\n",
    'expanded': "v='alpha beta'; \"$PROBE\" copy <<DOC\nvar=$v\narithmetic=$((9+4))\nsub=$(printf 'sub\\n\\n')\nbacktick=`printf tick`\nescaped=\\$v\nDOC\n",
    'strip_tabs': '"$PROBE" copy <<-DOC\n\tfirst\n\t\tsecond\n \tthird\n\tDOC\n',
    'sealed_read_only': '"$PROBE" read_only <<DOC\noriginal_document\nDOC\n',
    'empty': '"$PROBE" copy <<DOC\nDOC\n',
    'multiple': '"$PROBE" copy <<FIRST <<SECOND\nignored_first\nFIRST\nlast_document\nSECOND\n',
    'builtin_restore': "read v <<'DOC'\nbuiltin_value\nDOC\nprintf 'builtin=<%s>\\n' \"$v\"\nprintf 'stdout_restored\\n'\n",
    'pipeline_source': '"$PROBE" copy <<DOC | "$PROBE" copy\npipeline_document\nDOC\n',
    'pipeline_override': '"$PROBE" copy </out/c3_empty | "$PROBE" copy <<DOC\nlast_stdin_document\nDOC\n',
    'command_substitution': "v=$(\"$PROBE\" copy <<DOC\nsubstitution_document\nDOC\n); printf 'captured=<%s>\\n' \"$v\"\n",
    'redirection_failure_cleanup': "if \"$PROBE\" copy <<DOC >/missing/c3_file; then printf BAD; else printf 'C3_REDIR_RECOVERED\\n'; fi\nunused_document\nDOC\n",
    'large': '"$PROBE" copy <<\'C3_LARGE\'\n'+LARGE+'C3_LARGE\n',
}
MAIN = '''/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include "value.h"
#include "generated.h"
int main(void) { printf("C3_C value=%d generated=%d\\n",value(),generated_value()); return value()!=42 || generated_value()!=17; }
'''
REPAIRED_MAIN = MAIN.replace('generated=%d\\n','generated=%d repaired=1\\n')
GENERATED_HEADER = '/* SPDX-License-Identifier: Apache-2.0 */\nint generated_value(void);\n'
GENERATED_SOURCE = '/* SPDX-License-Identifier: Apache-2.0 */\n#include "generated.h"\nint generated_value(void) { return 17; }\n'
BUILD_CYCLE = b'main\nvalue\ngenerated\nlink_c\ncpp\nlink_cpp\n'


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):digest.update(data)
    return digest.hexdigest()


def reserved_snapshot(path):
    """Read only the private FAT32 root and hash reserved backing-file bytes."""
    with Path(path).open('rb') as stream:
        boot=stream.read(512)
        if boot[82:90]!=b'FAT32   ' or struct.unpack_from('<H',boot,11)[0]!=512:raise AssertionError('expected FAT32 private test image')
        sectors=boot[13];reserved=struct.unpack_from('<H',boot,14)[0];fats=boot[16]
        fat_size=struct.unpack_from('<I',boot,36)[0];root=struct.unpack_from('<I',boot,44)[0]
        total=struct.unpack_from('<I',boot,32)[0];first=reserved+fats*fat_size
        if total*512!=Path(path).stat().st_size or not sectors:raise AssertionError('invalid FAT geometry')
        maximum=(total-first)//sectors+1
        def chain(cluster):
            seen=set()
            while cluster<0xffffff8:
                if not 2<=cluster<=maximum or cluster in seen:raise AssertionError('invalid FAT chain')
                seen.add(cluster);stream.seek((first+(cluster-2)*sectors)*512)
                value=stream.read(sectors*512)
                if len(value)!=sectors*512:raise AssertionError('short FAT cluster')
                yield value
                stream.seek(reserved*512+cluster*4);raw=stream.read(4)
                if len(raw)!=4:raise AssertionError('short FAT entry')
                cluster=struct.unpack('<I',raw)[0]&0xfffffff
        entries=[]
        for block in chain(root):
            ended=False
            for offset in range(0,len(block),32):
                item=block[offset:offset+32]
                if item[0]==0:ended=True;break
                if item[0]==0xe5 or item[11]==0xf or item[11]&0x18:continue
                name=item[:8].decode('ascii',errors='replace').rstrip() + '.' + item[8:11].decode('ascii',errors='replace').rstrip()
                if name.startswith('XOS') and name.endswith('.TMP'):entries.append((name,item))
            if ended:break
        result={}
        for name,item in entries:
            length=struct.unpack_from('<I',item,28)[0];cluster=(struct.unpack_from('<H',item,20)[0]<<16)|struct.unpack_from('<H',item,26)[0]
            digest=hashlib.sha256();remaining=length
            if remaining:
                for block in chain(cluster):
                    amount=min(remaining,len(block));digest.update(block[:amount]);remaining-=amount
                    if not remaining:break
                if remaining:raise AssertionError('truncated reserved file')
            result[name]={'bytes':length,'cluster':cluster,'sha256':digest.hexdigest()}
        return result


def generation_script(main):
    text='PATH=/usr/bin:/bin:/; export PATH\n'
    for name,body in (('main.c',main),('generated.h',GENERATED_HEADER),('generated.c',GENERATED_SOURCE)):
        text+='/out/c3_probe save /src/c3demo/'+name+" <<'C3_SOURCE'\n"+body+'C3_SOURCE\n'
    return text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system',required=True,type=Path)
    parser.add_argument('--dash-manifest',required=True,type=Path)
    parser.add_argument('--make-manifest',required=True,type=Path)
    parser.add_argument('--sbase-manifest',type=Path)
    parser.add_argument('--release-images',required=True,type=Path)
    parser.add_argument('--report',type=Path,default=ROOT/'build/dash_c3_report.json')
    parser.add_argument('--artifacts',type=Path,default=ROOT/'build/dash_c3_evidence')
    args=parser.parse_args();args.system=args.system.resolve();args.artifacts=args.artifacts.resolve()/uuid.uuid4().hex
    args.artifacts.mkdir(parents=True,exist_ok=False)
    system=json.loads((args.system/'manifest.json').read_text());dash=json.loads(args.dash_manifest.read_text());make=json.loads(args.make_manifest.read_text())
    report={'phase':'C3_here_document_and_make','status':'failed','source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'system_build_id':system['build_id'],'image_sha256':sha(args.system/'xos.img'),'sdk_manifest_sha256':sha(args.system/'sdk/manifest.json'),
        'dash_sha256':dash['sha256'],'dash_manifest_sha256':sha(args.dash_manifest),'make_sha256':make['sha256'],'make_manifest_sha256':sha(args.make_manifest),'make_commit':make['commit'],'make_profile':make['profile'],'host_tools':system['tools'],'make_build_tools':make['tools'],
        'commands':[],'checks':[],'inputs':{},'host_reference':{},'exports':{},'artifacts':str(args.artifacts),
        'not_run':['C3_exec_identity_and_failure_atomicity_qualified_by_separate_runner','SMP','unrelated_long_randomized_stress']}
    guest=None
    try:
        if report['image_sha256']!=system['artifacts']['xos.img']['sha256']:raise AssertionError('system image mismatch')
        if make['commit']!='c546c3a5724c81cee9a11d816a38ccdf17472129':raise AssertionError('unexpected Make source commit')
        sdk=args.system/'sdk';sdk_info=json.loads((sdk/'manifest.json').read_text())
        if sdk_info['build_id']!=system['build_id'] or make['sdk_manifest_sha256']!=sha(sdk/'manifest.json'):raise AssertionError('SDK/Make build input mismatch')
        dash_elf=ROOT/dash['elf'];make_elf=ROOT/make['elf']
        for elf,wanted in ((dash_elf,dash['sha256']),(make_elf,make['sha256'])):
            if sha(elf)!=wanted:raise AssertionError('ELF does not match manifest: '+str(elf))
        with tempfile.TemporaryDirectory(prefix='xos_dash_c3_') as temporary:
            folder=Path(temporary);disk=folder/'work.img';probe=folder/'c3_probe';native=folder/'native_probe'
            source=FIXTURES/'io_probe.c';build_probe(source,probe,sdk)
            report['inputs']['probe']={'source_sha256':sha(source),'elf_sha256':sha(probe)}
            shutil.copy2(probe,args.artifacts/'c3_probe.elf')
            service_source=FIXTURES/'anonymous_service.cpp';service_probe=folder/'anonymous_service'
            build_probe(service_source,service_probe,sdk)
            report['inputs']['anonymous_service_probe']={'source_sha256':sha(service_source),'elf_sha256':sha(service_probe)}
            shutil.copy2(service_probe,args.artifacts/'anonymous_service.elf')
            subprocess.run([shutil.which('clang') or 'cc','-O2','-DXOS_REFERENCE',str(source),'-o',str(native)],check=True)
            report['disk_input']=prepare_release_disk(args.release_images,disk)
            for directory in ('/tests','/out','/src','/tmp'):ensure_directory(disk,directory)
            for directory in ('/src/c3demo','/src/make','/out/c3demo','/xos_sdk'):transfer(disk,'mkdir',directory)
            for target,binary in (('/usr/bin/dash',dash_elf),('/usr/bin/make',make_elf),('/out/c3_probe',probe),('/out/c3_anon_service',service_probe)):transfer(disk,'import',target,binary)
            if args.sbase_manifest:
                sbase=json.loads(args.sbase_manifest.read_text());report['sbase_manifest_sha256']=sha(args.sbase_manifest)
                for item in sbase['tools'].values():
                    binary=ROOT/item['path']
                    if sha(binary)!=item['sha256']:raise AssertionError('sbase ELF mismatch')
                    transfer(disk,'import',item['guest_path'],binary)
            # Build against this SDK in a new path. The pinned release sysroot
            # and its compiler binaries remain byte-for-byte untouched inputs.
            sdk_files={}
            for path in sorted(sdk.rglob('*')):
                relative=path.relative_to(sdk).as_posix();target='/xos_sdk/'+relative
                if path.is_dir():transfer(disk,'mkdir',target)
                elif path.is_file():transfer(disk,'import',target,path);sdk_files[relative]=sha(path)
            report['inputs']['guest_sdk_files']=sdk_files
            source_dir=Path(make.get('source_dir',ROOT/Path(make['elf']).parent/'source'))
            if not source_dir.is_absolute():source_dir=ROOT/source_dir
            adapted={}
            for name in ('main.c','parser.c','rules.c','defaults.c','make.h'):
                path=source_dir/name;wanted=make['adapted_sources'][name]
                if sha(path)!=wanted:raise AssertionError('adapted Make source mismatch: '+name)
                transfer(disk,'import','/src/make/'+name,path);adapted[name]=wanted
            backend=ROOT/'src/ports/make/posix_xos.cpp'
            if sha(backend)!=make['inputs']['src/ports/make/posix_xos.cpp']:raise AssertionError('Make backend source mismatch')
            transfer(disk,'import','/src/make/posix_xos.cpp',backend);adapted['posix_xos.cpp']=sha(backend)
            original=ROOT/'src/ports/make/upstream/make/posix.c'
            if sha(original)!=make['inputs']['src/ports/make/upstream/make/posix.c']:raise AssertionError('upstream posix.c provenance mismatch')
            transfer(disk,'import','/src/make/posix.c',original);adapted['posix.c_uncompiled_original']=sha(original)
            license_file=ROOT/'src/ports/make/upstream/LICENSE'
            if sha(license_file)!=make['inputs']['src/ports/make/upstream/LICENSE']:raise AssertionError('Make LICENSE provenance mismatch')
            transfer(disk,'import','/src/make/LICENSE',license_file);adapted['LICENSE']=sha(license_file)
            report['inputs']['guest_make_project']={'sources':adapted,'makefile_sha256':sha(FIXTURES/'C3MakeSelf.mk'),'host_build_commands':make['commands']}
            for path in sorted(FIXTURES.iterdir()):
                if path.suffix in ('.mk','.specs'):target='/tests/'+path.name
                elif path.name in ('value.h','value.c','app.cpp'):target='/src/c3demo/'+path.name
                elif path.name in ('c3_posix_direct.sh','c3_wrong_shebang.sh'):target='/tests/'+path.name
                else:continue
                transfer(disk,'import',target,path);report['inputs'][target]=sha(path)
            empty=folder/'empty';empty.write_bytes(b'');transfer(disk,'import','/out/c3_empty',empty)
            # A pre-existing unknown-owner reserved file forces CREATE_NEW's
            # collision branch. Direct helper import is confined to this new
            # private image; ordinary transfer intentionally denies this name.
            initial_reserved=reserved_snapshot(disk)
            if 'XOS00000.TMP' not in initial_reserved:
                collision=folder/'reserved_collision';collision.write_bytes(b'C3_PREEXISTING_RESERVED_KEEP\n')
                subprocess.run([str(host_tool()),str(disk),'import','/XOS00000.TMP',str(collision)],check=True)
            reserved_before=reserved_snapshot(disk);report['reserved_files_before']=reserved_before
            expected={}
            scripts={}
            for name,body in HERE_CASES.items():
                text='PROBE=/out/c3_probe; export PROBE\n{\n'+body+'} > /out/c3_here_'+name+'.stdout\n'
                scripts['here_'+name]=text
                host_body=body.replace('/out/c3_empty',str(empty)).replace('/missing/c3_file',str(folder/'missing_reference_parent/file'))
                reference=subprocess.run(['/bin/sh','-c',host_body],env={'PROBE':str(native),'PATH':'/usr/bin:/bin'},capture_output=True,timeout=30)
                if reference.returncode:raise AssertionError('host HereDoc reference failed: '+name)
                expected[name]=reference.stdout
                (args.artifacts/('here_'+name+'.reference')).write_bytes(reference.stdout)
                report['host_reference'][name]={'shell':'/bin/sh','input':host_body,'exit':reference.returncode,'stdout_sha256':hashlib.sha256(reference.stdout).hexdigest(),'bytes':len(reference.stdout),'stderr':reference.stderr.decode(errors='replace')}
            scripts.update({
                'generate':generation_script(MAIN),
                'repair':generation_script(REPAIRED_MAIN),
                'bad_source':"/out/c3_probe save /src/c3demo/main.c <<'BAD_SOURCE'\nint main(void) { this is a syntax error; }\nBAD_SOURCE\n",
                'build':"PATH=/usr/bin:/bin:/; export PATH\nmake -B -f /tests/C3Project.mk all\n",
                'run_apps':"/out/c3demo/c.elf && /out/c3demo/cpp.elf\n",
                'self_build':"PATH=/usr/bin:/bin:/; export PATH\nmake -B -f /tests/C3MakeSelf.mk all\n",
                'self_make_exec':"PATH=/usr/bin:/bin:/; export PATH\nexec /out/make -B -f /tests/C3Exec.mk all\nprintf C3_EXEC_SHOULD_NOT_RETURN\n",
                'self_make_consumer':"PATH=/usr/bin:/bin:/; export PATH\n/out/make -B -f /tests/C3Project.mk all && /out/c3demo/c.elf && /out/c3demo/cpp.elf\n",
            })
            scripts['legacy_spawn_driver']='/usr/bin/x86_64-elf-gcc --version > /out/c3_legacy_spawn.stdout\n'
            scripts['legacy_exec_driver']='exec /usr/bin/x86_64-elf-gcc --version > /out/c3_legacy_exec.stdout\nprintf SHOULD_NOT > /out/c3_legacy_after_exec.txt\n'
            report['legacy_crt_contract']={'ordinary_spawn_expected_exit':0,'explicit_exec_expected_exit':126,
                'exec_replaced_allowed':False,'post_exec_body_allowed':False,
                'redirection_note':'Shell creates/truncates stdout before exec; the expected empty file is an allowed redirection side effect, not a failed image-commit atomicity check'}
            # Direct script dispatch is a separately declared compatibility
            # path. Only the POSIX script is executed by the host reference;
            # the unsupported Python shebang has a guest-only reject contract.
            direct_body="cd /\nv=parent; e=before; export e; set -- p 'two words'\n/tests/c3_posix_direct.sh 'one two' ''\ns=$?\nprintf 'C3_DIRECT_PARENT status=%s v=%s e=%s cwd=%s argc=%s first=<%s> second=<%s>\\n' \"$s\" \"$v\" \"$e\" \"$PWD\" \"$#\" \"$1\" \"$2\"\nprintf 'C3_DIRECT_PARENT_CONTINUED\\n'\n"
            scripts['direct_script_driver']='{\n'+direct_body+'} > /out/c3_direct_script.stdout\n'
            scripts['rejected_shebang_driver']="{\nprintf 'C3_REJECT_BEGIN\\n'\n/tests/c3_wrong_shebang.sh\ns=$?\nprintf 'C3_REJECT status=%s\\n' \"$s\"\ntest \"$s\" -eq 126 || exit 92\nprintf 'C3_REJECT_RECOVERED\\n'\n} > /out/c3_wrong_script.stdout\n"
            native_script=folder/'posix_direct.sh'
            shutil.copy2(FIXTURES/'c3_posix_direct.sh',native_script);native_script.chmod(0o700)
            native_direct=direct_body.replace('/tests/c3_posix_direct.sh',str(native_script))
            direct_reference=subprocess.run(['/bin/sh','-c',native_direct],capture_output=True,env={'PATH':'/usr/bin:/bin'},timeout=30)
            if direct_reference.returncode:raise AssertionError('host direct script reference failed')
            direct_expected=direct_reference.stdout.replace(str(native_script).encode(),b'/tests/c3_posix_direct.sh')
            required_direct=(b'C3_DIRECT argc=2 arg1=<one two> arg2=<>',
                b'env=<before>',b'substitution=<captured> here=<literal $NO_EXPAND>',
                b'C3_DIRECT_PARENT status=17 v=parent e=before cwd=/ argc=2 first=<p> second=<two words>',
                b'C3_DIRECT_PARENT_CONTINUED')
            if any(marker not in direct_expected for marker in required_direct):raise AssertionError('host direct script reference does not meet the declared argument/status/isolation contract')
            report['host_reference']['direct_posix_script']={'shell':'/bin/sh','input':native_direct,'exit':direct_reference.returncode,
                'stdout':direct_expected.decode(errors='replace'),'stdout_sha256':hashlib.sha256(direct_expected).hexdigest(),
                'stderr':direct_reference.stderr.decode(errors='replace'),'path_normalization':'private native script path replaced with guest script path'}
            make_cases={
                'macros':('make -B -f /tests/C3Macros.mk MESSAGE=cli all',0),
                'diamond':('make -B -f /tests/C3Diamond.mk all',0),
                'dry':('make -B -n -f /tests/C3Dry.mk all',0),
                'ignore':('make -B -i -f /tests/C3Ignore.mk all',0),
                'prefix_ignore':('make -B -f /tests/C3PrefixIgnore.mk all',0),
                'keep':('make -B -k -f /tests/C3Keep.mk all','nonzero'),
                'cycle':('make -B -f /tests/C3Cycle.mk all','nonzero'),
                'question':('make -B -f /tests/C3Question.mk all','nonzero'),
                'plus':('make -B -n -f /tests/C3Plus.mk all','nonzero'),
                'pattern':('make -B -f /tests/C3Pattern.mk all','nonzero'),
                'suffix':('make -B -f /tests/C3Suffix.mk all','nonzero'),
                'missing_dep':('make -B -f /tests/C3MissingDep.mk all','nonzero'),
                'recursive_macro':('make -B -f /tests/C3RecursiveMacro.mk all','nonzero'),
                'no_B':('make -f /tests/C3Dry.mk all','nonzero'),
                'missing_f_operand':('make -B -f','nonzero'),
                'missing_makefile':('make -B -f /missing/C3.mk','nonzero'),
                'option_j':('make -B -j 2 -f /tests/C3Dry.mk all','nonzero'),
                'option_q':('make -B -q -f /tests/C3Dry.mk all','nonzero'),
                'option_t':('make -B -t -f /tests/C3Dry.mk all','nonzero'),
                'option_r':('make -B -r -f /tests/C3Dry.mk all','nonzero'),
                'other_shell':('make -B -f /tests/C3Dry.mk SHELL=/bin/sh all','nonzero'),
                'fault_i':('make -B -i -f /tests/C3Fault.mk all',137),
            }
            for name,(line,code) in make_cases.items():scripts['make_'+name]='PATH=/usr/bin:/bin:/; export PATH\n'+line+'\n'
            report['scripts']={}
            for name,text in scripts.items():
                path=args.artifacts/(name+'.sh');path.write_text('# SPDX-License-Identifier: Apache-2.0\n'+text)
                transfer(disk,'import','/tests/c3_'+name+'.sh',path)
                report['scripts'][name]={'input':text,'sha256':sha(path)}
            guest=Guest(args.system/'xos.img','dash_c3',work_disk=disk)
            report['qemu_command']=guest.command;report['qemu_version']=subprocess.check_output([guest.command[0],'--version'],text=True).splitlines()[0]
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r');guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
            baseline=resources(guest);report['baseline_resources']=baseline

            def run(name,line,expected_code=0,markers=(),timeout=180):
                record={'name':name,'command':line,'expected_exit':expected_code,'status':'failed'};report['commands'].append(record);start=len(guest.output)
                try:
                    output=command(guest,line,b'kind=exited code=',timeout=timeout)
                    match=re.search(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)',output)
                    code=int(match[1]) if match else None
                    record.update(actual_exit=code,output=output.decode(errors='replace'))
                    if code is None or (code==0 if expected_code=='nonzero' else code!=expected_code):raise AssertionError(f'{name}: exit {code} expected {expected_code}')
                    for marker in markers:
                        if marker not in output:raise AssertionError(f'{name}: missing {marker!r}')
                    after=resources(guest);record['resources_after']=after
                    if after!=baseline:raise AssertionError(f'{name}: resources {after} != {baseline}')
                    record['status']='passed';report['checks'].append(name);return output
                finally:
                    log=args.artifacts/(name+'.serial.log');log.write_bytes(bytes(guest.output[start:]));record['serial_sha256']=sha(log)

            run('guest_gcc_version','exec-file /usr/bin/x86_64-elf-gcc --version',0,(b'16.2.0',))
            run('guest_gxx_version','exec-file /usr/bin/x86_64-elf-g++ --version',0,(b'16.2.0',))
            run('anonymous_capacity_reuse_and_reserved_paths','exec-file /out/c3_probe anonymous',0,(b'C3_ANON slots=16',))
            run('anonymous_fork_refcount_and_last_close','exec-driver /out/c3_probe anonymous_share',0,(b'fork_reference_survives_parent_close',))
            run('anonymous_service_seal_applies_to_fork_and_transfer','exec-driver /out/c3_anon_service',0,(b'C3_ANON_SERVICE seal=shared fork=readonly transfer=readonly',))
            for name in HERE_CASES:run('heredoc_'+name,'dash /tests/c3_here_'+name+'.sh',0)
            run('direct_posix_script_dispatch_and_parent_isolation','dash /tests/c3_direct_script_driver.sh',0)
            run('unsupported_shebang_explicit_126_without_body','dash /tests/c3_rejected_shebang_driver.sh',0)
            run('legacy_gcc_ordinary_spawn_still_supported','dash /tests/c3_legacy_spawn_driver.sh',0)
            legacy_failure=run('legacy_gcc_explicit_exec_rejected_before_replace','dash /tests/c3_legacy_exec_driver.sh',126)
            if b'exec_replaced' in legacy_failure or b'SHOULD_NOT' in legacy_failure:
                raise AssertionError('unsupported legacy exec committed an image or ran its following Shell body')
            run('legacy_exec_following_body_did_not_run','exec-file /out/c3_probe absent /out/c3_legacy_after_exec.txt',0,(b'C3_ABSENT verified',))
            run('script_fallback_does_not_install_bin_sh_alias','exec-file /out/c3_probe absent /bin/sh',0,(b'C3_ABSENT verified',))
            run('guest_here_document_generates_project_sources','dash /tests/c3_generate.sh')
            run('real_make_compiles_c_and_gxx_project','dash /tests/c3_build.sh',0,timeout=600)
            run('guest_generated_c_cpp_programs_execute','dash /tests/c3_run_apps.sh',0,(b'C3_C value=42 generated=17',b'C3_CPP real_gxx value=42'))
            run('second_explicit_B_rebuild','dash /tests/c3_build.sh',0,timeout=600)
            run('install_intentional_bad_source','dash /tests/c3_bad_source.sh')
            run('make_propagates_real_compiler_syntax_error','dash /tests/c3_build.sh','nonzero',(b'error:',),timeout=600)
            run('repair_source_using_heredoc','dash /tests/c3_repair.sh')
            run('make_rebuilds_after_source_repair','dash /tests/c3_build.sh',0,timeout=600)
            run('repaired_binary_not_stale','dash /tests/c3_run_apps.sh',0,(b'generated=17 repaired=1',b'C3_CPP real_gxx value=42'))
            for name,(line,code) in make_cases.items():run('make_'+name,'dash /tests/c3_make_'+name+'.sh',code,timeout=90)
            for path in ('/out/c3_dry_created.txt','/out/c3_plus_bad.txt'):
                run('absent_'+Path(path).name,'exec-file /out/c3_probe absent '+path,0,(b'C3_ABSENT verified',))
            run('upstream_make_compiles_itself_inside_xos','dash /tests/c3_self_build.sh',0,timeout=1200)
            run('guest_self_built_make_consumes_project','dash /tests/c3_self_make_consumer.sh',0,(b'generated=17 repaired=1',b'C3_CPP real_gxx value=42'),timeout=600)

            output=run('explicit_exec_guest_self_built_make_same_pid','dash /tests/c3_self_make_exec.sh',0,
                (b'C3_EXEC_NATIVE_MAKE=ok',b'file_session_rekeyed=1 old_spawn_depth=3 spawn_depth=2'))
            if b'C3_EXEC_SHOULD_NOT_RETURN' in output:raise AssertionError('explicit exec returned to old Dash')
            start=len(guest.output);send_bytes(guest,b'dash -i\r');guest.expect(b'$ ',start=start,timeout=60)
            for name,line,ready in (
                ('heredoc_kill_cleanup',b"/out/c3_probe spin <<'C3_KILL'\nheld_anonymous_input\nC3_KILL\r",b'C3_SPIN_READY'),
                ('make_external_escape_not_ignored',b'make -B -i -f /tests/C3CancelExternal.mk all\r',b'C3_SPIN_READY'),
                ('make_recipe_shell_escape',b'make -B -s -f /tests/C3CancelBuiltin.mk all\r',b'C3_RECIPE_SHELL_READY')):
                start=len(guest.output);send_bytes(guest,line);guest.expect(ready,start=start,timeout=90);pump(guest,.3);send_bytes(guest,b'\x1b');guest.expect(b'$ ',start=start,timeout=90)
                cancelled=bytes(guest.output[start:]);recovery_start=len(guest.output)
                send_bytes(guest,b"printf 'C3_CANCEL_STATUS=%d\\n' $?\r")
                guest.expect(b'C3_CANCEL_STATUS=137',start=recovery_start,timeout=60);guest.expect(b'$ ',start=recovery_start,timeout=60)
                output=cancelled+bytes(guest.output[recovery_start:])
                if b'cancelled_by_escape' not in cancelled:raise AssertionError(name+': no actual Escape cancellation evidence')
                report['commands'].append({'name':name,'status':'passed','expected_exit':137,'actual_exit':137,'output':output.decode(errors='replace')});report['checks'].append(name)
                (args.artifacts/(name+'.serial.log')).write_bytes(output)
            start=len(guest.output);send_bytes(guest,b'exit\r');guest.expect_supervisor(start=start,timeout=60);pump(guest,.5)
            if resources(guest)!=baseline:raise AssertionError('interactive cancel/anonymous cleanup leaked')
            for path in ('/out/c3_cancel_bad.txt','/out/c3_cancel_builtin_bad.txt'):
                run('absent_'+Path(path).name,'exec-file /out/c3_probe absent '+path,0,(b'C3_ABSENT verified',))
            command(guest,'sync',b'[files] sync=ok',timeout=60);report['final_resources']=resources(guest)
            guest.close();guest=None
            reserved_after=reserved_snapshot(disk);report['reserved_files_after']=reserved_after
            if set(reserved_after)-set(reserved_before):raise AssertionError('anonymous backing files remain after close/failure/kill')
            for name,item in reserved_before.items():
                if name in ('XOSTMP.TMP','XOSBAK.TMP','XOSJRNL.TMP'):continue
                if name not in reserved_after or reserved_after[name]['sha256']!=item['sha256'] or reserved_after[name]['bytes']!=item['bytes']:raise AssertionError('pre-existing reserved file changed: '+name)
            report['checks'].append('anonymous_backings_closed_and_collision_files_preserved_offline')
            def export(name,path,wanted=None):
                destination=args.artifacts/name;transfer(disk,'export',path,destination);data=destination.read_bytes()
                report['exports'][path]={'path':str(destination),'bytes':len(data),'sha256':sha(destination)}
                if wanted is not None and data!=wanted:raise AssertionError('complete byte comparison failed: '+path)
                return data
            legacy_version=export('legacy_spawn.guest','/out/c3_legacy_spawn.stdout')
            if b'16.2.0' not in legacy_version:raise AssertionError('legacy GCC spawn version stdout is missing actual 16.2.0 output')
            export('legacy_exec_rejected.guest','/out/c3_legacy_exec.stdout',b'')
            export('direct_posix_script.guest','/out/c3_direct_script.stdout',direct_expected)
            export('unsupported_shebang.guest','/out/c3_wrong_script.stdout',b'C3_REJECT_BEGIN\nC3_REJECT status=126\nC3_REJECT_RECOVERED\n')
            for name,wanted in expected.items():export('here_'+name+'.guest','/out/c3_here_'+name+'.stdout',wanted)
            for name,wanted in (('main.c',REPAIRED_MAIN),('generated.h',GENERATED_HEADER),('generated.c',GENERATED_SOURCE)):export(name+'.guest','/src/c3demo/'+name,wanted.encode())
            count=export('build_count.guest','/out/c3demo/build_count.txt')
            # Two normal builds, one failed main compile, a repaired build and
            # a complete rebuild performed by the Make executable built in XOS.
            wanted_count=BUILD_CYCLE*2+b'main\n'+BUILD_CYCLE*2
            if count!=wanted_count:raise AssertionError('explicit -B did not execute expected rebuild recipes: '+repr(count))
            export('macros.guest','/out/c3_macros.txt',b'cli:all:/tests/C3Config.mk:dash\n')
            export('diamond.guest','/out/c3_diamond.txt',b'shared\nleft\nright\n')
            export('ignored.guest','/out/c3_ignored.txt',b'ignore_continued\n')
            export('prefix_ignored.guest','/out/c3_prefix_ignored.txt',b'prefix_continued\n')
            export('kept.guest','/out/c3_kept.txt',b'keep_independent\n')
            export('keep.guest','/out/c3_keep.txt',b'keep')
            for name,path in (('guest_self_built_make.elf','/out/make'),('c_demo.elf','/out/c3demo/c.elf'),('cpp_demo.elf','/out/c3demo/cpp.elf')):
                data=export(name,path)
                if data[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',data,18)[0]!=62:raise AssertionError('guest build did not produce x86-64 ELF: '+path)
            report['checks'].append('full_heredoc_source_build_count_and_project_artifact_comparisons')
            report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest:report['output_tail']=bytes(guest.output[-24000:]).decode(errors='replace')
        raise
    finally:
        if guest:guest.close()
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
