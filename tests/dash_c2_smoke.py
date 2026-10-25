# SPDX-License-Identifier: Apache-2.0
"""Qualify real C2 fork/isolation, pipelines and command substitution in XOS."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests')]
from boot_smoke import Guest
from dash_b2_smoke import build_probe
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer

# Every reference case captures its own stdout as a regular guest file. Kernel
# UART diagnostics therefore cannot be silently filtered into expected data.
CASES = {
    'builtin_pipeline': (0, "printf 'builtin words\\n' | \"$PROBE\" copy\nprintf 'last=%s\\n' \"$?\"\n"),
    'function_pipeline': (0, "v=parent; e=envparent; export e; set -- 'one two' ''; readonly ro=fixed\ng() { printf 'original_function\\n'; }\nf() { v=child; e=child; export e; cd /tmp; set -- changed; g() { printf 'child_function\\n'; }; printf '%s:%s:%s:%s:%s\\n' \"$v\" \"$e\" \"$1\" \"$ro\" \"$PWD\"; }\nf | \"$PROBE\" copy\nprintf 'parent=%s:%s:%s:%s:%s:%s\\n' \"$v\" \"$e\" \"$1\" \"$#\" \"$ro\" \"$PWD\"\ng\n"),
    'subshell_state': (0, "v=parent; export C2_EXPORTED=before; set -- 'alpha beta' ''; readonly fixed=immutable\ng() { printf 'parent_function\\n'; }\n(v=child; C2_EXPORTED=after; export C2_EXPORTED; cd /tmp; set -- child; g() { printf 'child_function\\n'; }; printf 'child=%s:%s:%s:%s:%s\\n' \"$v\" \"$C2_EXPORTED\" \"$1\" \"$fixed\" \"$PWD\"; g)\nprintf 'parent=%s:%s:%s:%s:%s:%s\\n' \"$v\" \"$C2_EXPORTED\" \"$1\" \"$#\" \"$fixed\" \"$PWD\"\ng\n"),
    'local_variable': (0, "f() { local v=inside; (v=child; printf 'child=%s\\n' \"$v\"); printf 'local=%s\\n' \"$v\"; }; v=outside; f; printf 'global=%s\\n' \"$v\"\n"),
    'arithmetic_stage_isolation': (0, "x=5; \"$PROBE\" echo \"$((x=x+1))\" | \"$PROBE\" copy; printf 'parent_x=%s\\n' \"$x\"\nfalse; printf 'before=%s\\n' \"$?\" | \"$PROBE\" copy; printf 'after=%s\\n' \"$?\"\n"),
    'substitution_forms': (0, "a=$(printf 'one\\n\\n\\n'); b=`printf 'two\\n\\n'`; c=$(printf ''); printf 'a=<%s> b=<%s> c=<%s>\\n' \"$a\" \"$b\" \"$c\"\nv=parent; d=$(v=child; cd /tmp; printf '%s:%s' \"$v\" \"$PWD\"); printf 'captured=<%s> parent=%s:%s\\n' \"$d\" \"$v\" \"$PWD\"\n"),
    'substitution_exit_status': (0, "a=$(printf 'value\\n'; exit 23); s=$?; printf 'capture=<%s> status=%s\\n' \"$a\" \"$s\"\nb=$(false); s=$?; printf 'empty=<%s> status=%s\\n' \"$b\" \"$s\"\n"),
    'substitution_large': (0, "value=$(\"$PROBE\" text 32781); printf 'length=%s\\n' \"${#value}\"; printf '%s' \"$value\" | \"$PROBE\" check 32781\n"),
    'substitution_three_levels': (0, "a=$(b=$(c=$(printf nested); printf '%s' \"$c\"); printf '%s' \"$b\"); printf 'nested=<%s>\\n' \"$a\"\n"),
    'subshell_status': (23, "(printf 'subshell_status\\n'; exit 23)\n"),
    'function_pipeline_status': (0, "f() { printf data; return 17; }; g() { \"$PROBE\" copy; return 29; }; f | g; s=$?; printf '\\nlast_status=%s\\n' \"$s\"; test \"$s\" -eq 29\n"),
    'errexit_tested_pipeline_functions': (0, "set -e\nf() { false; printf 'tested_function_continued\\n'; }\nif f | \"$PROBE\" copy; then printf 'if_pipeline_ok\\n'; else printf 'BAD_IF_BRANCH\\n'; fi\nf | \"$PROBE\" copy && printf 'and_pipeline_ok\\n'\nprintf 'set_e_parent_continued\\n'\n"),
    'pipefail_rightmost_status': (0, "set -o pipefail\nf() { return 7; }; g() { return 23; }; f | g | true; printf 'rightmost=%s\\n' \"$?\"\nfalse | true; printf 'left_failure=%s\\n' \"$?\"\ntrue | false | true; printf 'middle_failure=%s\\n' \"$?\"\ntrue | true; printf 'all_success=%s\\n' \"$?\"\nset +o pipefail; false | true; printf 'pipefail_off=%s\\n' \"$?\"\n"),
    'descriptor_restore': (0, "f() { printf 'child_file\\n' > {OUT}/child_marker; }; f | \"$PROBE\" copy; printf 'parent_stdout_restored\\n'\n(printf 'subshell_file\\n' > {OUT}/sub_marker); printf 'parent_again\\n'\n"),
}
GUEST_CASES = {
    'depth_limit': (0, "a=$(b=$(c=$(d=$(printf UNREACHABLE_DEPTH)))); s=$?; if test \"$s\" -eq 0; then printf C2_DEPTH_BAD; exit 90; fi; printf 'C2_DEPTH_RECOVERED status=%s\\n' \"$s\"\n", (b'C2_DEPTH_RECOVERED',), (b'C2_DEPTH_BAD', b'UNREACHABLE_DEPTH')),
    'fault_substitution': (0, "a=$(\"$PROBE\" fault); s=$?; printf 'fault_capture=<%s> status=%s\\n' \"$a\" \"$s\"; test \"$s\" -eq 137\n", (b'fault_capture=<> status=137',), ()),
    'fork_exhaustion': (2, "f() { while :; do :; done; }; f | f | f | f\n", (), ()),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def threaded_probe(source, sdk, folder):
    cc = shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc'
    cxx = shutil.which('x86_64-elf-g++') or 'x86_64-elf-g++'
    obj, elf = folder/'threaded_probe.o', folder/'threaded_probe'
    flags = ['-B'+str(ROOT/'build/target_tools')+'/', '-O2', '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector']
    commands = [
        [cc, *flags, '-DXOS_THREADED_RUNTIME', '-I'+str(sdk/'include'), '-c', str(source), '-o', str(obj)],
        [cxx, *flags, '-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096', '-T', str(sdk/'user.ld'), str(sdk/'crt0_posix.o'), str(obj), '-Wl,--start-group', str(sdk/'lib/libxos.a'), str(sdk/'lib/libxos_loader.a'), str(sdk/'cpp/lib/libstdc++.a'), str(sdk/'cpp/lib/libsupc++.a'), str(sdk/'lib/libc.a'), str(sdk/'lib/libm.a'), str(sdk/'cpp/lib/libgcc.a'), '-Wl,--end-group', '-o', str(elf)],
    ]
    for line in commands: subprocess.run(line, check=True)
    return elf, commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', required=True, type=Path)
    parser.add_argument('--dash-manifest', required=True, type=Path)
    parser.add_argument('--threading-sdk', type=Path)
    parser.add_argument('--only-fork-oom', action='store_true', help='run the single allocation/fork ENOMEM rollback guest case only')
    parser.add_argument('--fork-oom-mib', type=int, default=254, help='target parent allocation size, 200..254 MiB; actual fork must fail ENOMEM')
    parser.add_argument('--report', type=Path, default=ROOT/'build/dash_c2_report.json')
    parser.add_argument('--artifacts', type=Path, default=ROOT/'build/dash_c2_evidence')
    args = parser.parse_args()
    if not 200 <= args.fork_oom_mib <= 254: parser.error('--fork-oom-mib must be 200..254')
    args.system = args.system.resolve()
    args.artifacts = args.artifacts.resolve()/uuid.uuid4().hex
    args.artifacts.mkdir(parents=True, exist_ok=False)
    system = json.loads((args.system/'manifest.json').read_text())
    dash = json.loads(args.dash_manifest.read_text())
    report = {'status': 'failed', 'phase': 'C2', 'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
              'system_build_id': system['build_id'], 'xos_sha256': sha(args.system/'xos.img'),
              'sdk_manifest_sha256': sha(args.system/'sdk/manifest.json'), 'dash_sha256': dash['sha256'],
              'artifacts': str(args.artifacts), 'only_fork_oom': args.only_fork_oom, 'fork_oom_mib': args.fork_oom_mib, 'commands': [], 'checks': [], 'host_reference': {}, 'side_effects': {},
              'not_run': ['SMP', 'long_randomized_stress', 'C3_here_document_exec_and_make'], 'tools': {}}
    guest = None
    try:
        assert report['xos_sha256'] == system['artifacts']['xos.img']['sha256'], 'system image mismatch'
        sdk_manifest = json.loads((args.system/'sdk/manifest.json').read_text())
        if sdk_manifest['build_id'] != system['build_id']: raise AssertionError('system SDK build ID mismatch')
        dash_elf = ROOT/dash['elf']
        assert sha(dash_elf) == dash['sha256'], 'dash ELF mismatch'
        source = ROOT/'tests/fixtures/dash_c2/fork_probe.c'
        report['probe_source_sha256'] = sha(source)
        for name in ('x86_64-elf-gcc','x86_64-elf-g++','nasm','clang'):
            executable = shutil.which(name)
            report['tools'][name] = {'path': executable, 'sha256': sha(executable),
                'version': subprocess.check_output([executable,'--version'], text=True).splitlines()[0]} if executable else None
        with tempfile.TemporaryDirectory(prefix='xos_dash_c2_') as folder_name:
            folder = Path(folder_name); disk = folder/'work.img'; probe = folder/'probe'; native = folder/'native_probe'
            build_probe(source, probe, args.system/'sdk')
            report['probe_sha256'] = sha(probe)
            shutil.copy2(probe, args.artifacts/'fork_probe.elf')
            subprocess.run([shutil.which('clang') or 'cc', '-O2', '-DXOS_REFERENCE', str(source), '-o', str(native)], check=True)
            create_fat32(disk,512)
            for directory in ('/usr','/usr/bin','/tests','/out','/tmp'): transfer(disk,'mkdir',directory)
            transfer(disk,'import','/usr/bin/dash',dash_elf); transfer(disk,'import','/out/probe',probe)
            if args.threading_sdk:
                sdk = args.threading_sdk.resolve()
                report['threading_sdk_manifest_sha256'] = sha(sdk/'manifest.json')
                threaded_manifest = json.loads((sdk/'manifest.json').read_text())
                for relative,digest in threaded_manifest['artifacts'].items():
                    if sha(sdk/relative) != digest: raise AssertionError('threading SDK artifact mismatch: '+relative)
                for relative,digest in threaded_manifest['inputs'].items():
                    if sha(ROOT/relative) != digest: raise AssertionError('threading SDK source mismatch: '+relative)
                elf, lines = threaded_probe(source,sdk,folder)
                report['threaded_probe'] = {'sha256': sha(elf), 'commands': lines}
                shutil.copy2(elf,args.artifacts/'fork_threaded_probe.elf')
                transfer(disk,'import','/out/threaded_probe',elf)
            else: report['not_run'].append('threaded_libc_fork_rejection_requires_threading_sdk')
            native_out = folder/'native_out'; native_out.mkdir()
            expected = {}
            report['scripts'] = {}
            for name,(code,body) in CASES.items():
                guest_body = body.replace('{OUT}','/out')
                text = "PROBE=/out/probe; export PROBE\ncd /\n{\n"+guest_body+"} > /out/"+name+".stdout\n"
                path = args.artifacts/(name+'.sh'); path.write_text('# SPDX-License-Identifier: Apache-2.0\n'+text)
                transfer(disk,'import','/tests/'+name+'.sh',path)
                host_body = body.replace('{OUT}',str(native_out))
                result = subprocess.run(['/bin/sh','-c',host_body], cwd='/', env={'PROBE':str(native),'PATH':'/usr/bin:/bin'}, capture_output=True, timeout=30)
                report['host_reference'][name] = {'shell':'/bin/sh','input':host_body,'expected_exit':code,'actual_exit':result.returncode,
                    'stdout':result.stdout.decode(errors='replace'),'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr':result.stderr.decode(errors='replace')}
                if result.returncode != code: raise AssertionError('host reference case failed: '+name)
                expected[name] = result.stdout
                (args.artifacts/(name+'.reference.stdout')).write_bytes(result.stdout)
                report['scripts'][name] = {'input':text,'sha256':sha(path),'expected_exit':code}
            for name,(code,body,markers,forbidden) in GUEST_CASES.items():
                text = "PROBE=/out/probe; export PROBE\ncd /\n{\n"+body+"} > /out/"+name+".stdout\n"
                path = args.artifacts/(name+'.sh'); path.write_text('# SPDX-License-Identifier: Apache-2.0\n'+text)
                transfer(disk,'import','/tests/'+name+'.sh',path)
                report['scripts'][name] = {'input':text,'sha256':sha(path),'expected_exit':code}
            # Compare the same low-level fork/FD probe with a native reference.
            native_file = folder/'fork_shared.bin'
            native_result = subprocess.run([str(native),'fork',str(native_file)],capture_output=True,timeout=30)
            if native_result.returncode != 0 or native_file.read_bytes() != b'abXdef':
                raise AssertionError('host fork probe failed')
            report['host_reference']['fork_probe'] = {'actual_exit':native_result.returncode,'stdout':native_result.stdout.decode(),
                'stderr':native_result.stderr.decode(),'file_sha256':sha(native_file)}

            guest = Guest(args.system/'xos.img','dash_c2',work_disk=disk)
            report['qemu_command'] = guest.command
            report['tools']['qemu'] = {'path':guest.command[0],'sha256':sha(guest.command[0]),
                'version':subprocess.check_output([guest.command[0],'--version'],text=True).splitlines()[0]}
            guest.expect(b'xos64> ',timeout=40); send_bytes(guest,b'run\r'); guest.expect_supervisor(trace=True,timeout=40); pump(guest,1.5)
            baseline = resources(guest); report['baseline_resources'] = baseline

            def run(name,line,code,markers=(),timeout=120,resource_target=None):
                record = {'name':name,'command':line,'expected_exit':code,'status':'failed'};report['commands'].append(record)
                start = len(guest.output)
                try:
                    output = command(guest,line,b'kind=exited code=',timeout=timeout)
                    match = re.search(rb'\[wait\] pid=\d+ kind=exited code=(-?\d+)',output)
                    actual = int(match[1]) if match else None
                    record.update(actual_exit=actual,output=output.decode(errors='replace'))
                    if name == 'real_fork_copy_ENOMEM_rollback':
                        record['resource_counters'] = [dict(phase=phase.decode(), **{key.decode():int(value) for key,value in re.findall(rb'(\w+)=(\d+)',fields)}) for phase,fields in re.findall(rb'C2_OOM_COUNTERS (\S+) ([^\r\n]+)',output)]
                        if [item['phase'] for item in record['resource_counters']] != ['initial','held','failed','after_free']: raise AssertionError('missing ENOMEM per-phase counters')
                    if actual != code: raise AssertionError(f'{name}: exit {actual} != {code}')
                    for marker in markers:
                        if marker not in output: raise AssertionError(f'{name}: missing {marker!r}')
                    after = resources(guest); record['resources_after'] = after
                    if after != (resource_target or baseline): raise AssertionError(f'{name}: resources {after} != {resource_target or baseline}')
                    record['status']='passed';report['checks'].append(name)
                    return output
                finally:
                    path = args.artifacts/(name+'.serial.log');path.write_bytes(bytes(guest.output[start:]));record['serial_sha256']=sha(path)

            oom_command = f'exec-driver /out/probe oom /out/oom_parent.bin {args.fork_oom_mib}'
            oom_markers = (b'C2_OOM fork_errno=ENOMEM', b'partial_child_resources=baseline parent_memory=valid parent_fd=valid PASS')
            if args.only_fork_oom:
                report['not_run'].append('other_C2_guest_cases_excluded_by_only_fork_oom')
                run('real_fork_copy_ENOMEM_rollback',oom_command,0,oom_markers,timeout=180)
                command(guest,'sync',b'[files] sync=ok',timeout=60)
                report['final_resources']=resources(guest)
                guest.close();guest=None
                exported=args.artifacts/'oom_parent.bin.guest';transfer(disk,'export','/out/oom_parent.bin',exported)
                if exported.read_bytes()!=b'beforeafter': raise AssertionError('ENOMEM parent file bytes changed')
                report['side_effects']['oom_parent.bin']={'bytes':11,'sha256':sha(exported)}
                report['status']='passed'
                print(json.dumps(report))
                return

            for iteration in range(3):
                run('low_level_eager_fork_memory_pid_and_open_description_'+str(iteration),'exec-driver /out/probe fork /out/fork_shared.bin',0,(b'C2_FORK memory=isolated',b'PASS'))
            run('fork_privilege_arguments_and_files_service_auth','exec-file /out/probe denied',0,(b'service_auth=denied PASS',))
            run('kernel_thread_profile_rejects_fork','exec-driver /out/probe profile',0,(b'thread_profile=ENOTSUP PASS',))
            if args.threading_sdk: run('threaded_libc_explicitly_rejects_fork','exec-file /out/threaded_probe threaded_reject',0,(b'threaded_libc=ENOTSUP PASS',))
            run('real_fork_copy_ENOMEM_rollback',oom_command,0,oom_markers,timeout=180)
            for name,(code,body) in CASES.items(): run(name,'dash /tests/'+name+'.sh',code)
            for name in ('depth_limit','fault_substitution'):
                code,body,markers,forbidden = GUEST_CASES[name]
                run(name,'dash /tests/'+name+'.sh',code)
            blockers=[]
            for _ in range(2):
                output=command(guest,'spawn-file /out/probe spin',b'[loader] started pid=',timeout=45)
                blockers.append(int(re.search(rb'\[loader\] started pid=(\d+)',output)[1]))
            occupied=resources(guest); report['quota_setup']={'pids':blockers,'resources':occupied}
            if occupied[1] != baseline[1]+2: raise AssertionError('quota blockers did not consume two task slots')
            run('fork_exhaustion_partial_pipeline_cleanup','dash /tests/fork_exhaustion.sh',2,resource_target=occupied)
            for pid in blockers:
                command(guest,f'kill {pid}',b'kill: accepted');command(guest,f'wait {pid}',b'kind=killed code=-9')
            if resources(guest)!=baseline: raise AssertionError('quota blocker cleanup leaked')

            # Cancellation while the parent is blocked on command-substitution
            # stdout must collect that environment and permit the Shell to run.
            start=len(guest.output);send_bytes(guest,b'dash -i\r');guest.expect(b'$ ',start=start,timeout=60)
            start=len(guest.output)
            send_bytes(guest,b"v=$(/out/probe spin); printf 'C2_CANCEL_RECOVERED status=%d\\n' $?\r")
            guest.expect(b'C2_SPIN_READY',start=start,timeout=60);send_bytes(guest,b'\x1b')
            guest.expect(b'C2_CANCEL_RECOVERED status=137',start=start,timeout=60);guest.expect(b'$ ',start=start,timeout=60)
            output=bytes(guest.output[start:])
            report['commands'].append({'name':'escape_cancels_substitution_and_recovers_shell','status':'passed','output':output.decode(errors='replace')})
            report['checks'].append('escape_cancels_substitution_and_recovers_shell')
            overflow_start=len(guest.output)
            send_bytes(guest,b'a=$(/out/probe text 1048701)\r')
            guest.expect(b'exceeds 1048576',start=overflow_start,timeout=180)
            guest.expect(b'$ ',start=overflow_start,timeout=60)
            overflow=bytes(guest.output[overflow_start:])
            recovery_start=len(guest.output)
            send_bytes(guest,b"printf 'C2_CAPTURE_LIMIT status=%d\\n' $?; b=$(printf recovered); printf 'C2_CAPTURE_AFTER=<%s> status=%d\\n' \"$b\" $?\r")
            guest.expect(b'C2_CAPTURE_LIMIT status=2',start=recovery_start,timeout=60)
            guest.expect(b'C2_CAPTURE_AFTER=<recovered> status=0',start=recovery_start,timeout=60)
            guest.expect(b'$ ',start=recovery_start,timeout=60)
            recovery=bytes(guest.output[recovery_start:])
            overflow_log=args.artifacts/'capture_limit_and_recovery.serial.log'
            overflow_log.write_bytes(overflow+recovery)
            report['commands'].append({'name':'command_substitution_capture_limit_recovers_shell',
                'status':'passed','producer_text_bytes':1048701,'producer_stdout_bytes':1048704,'capture_limit_bytes':1048576,
                'expected_overflow_status':2,'actual_overflow_status':2,
                'expected_recovery_status':0,'actual_recovery_status':0,
                'output':(overflow+recovery).decode(errors='replace'),
                'serial_sha256':sha(overflow_log)})
            report['checks'].append('command_substitution_capture_limit_recovers_shell')
            start=len(guest.output);send_bytes(guest,b'exit\r');guest.expect_supervisor(start=start,timeout=60);pump(guest,.5)
            if resources(guest)!=baseline: raise AssertionError('interactive substitution cancellation/capture-limit cleanup leaked')
            for repeat in range(3): run('repeated_isolation_reclamation_'+str(repeat),'dash /tests/substitution_forms.sh',0)
            command(guest,'sync',b'[files] sync=ok',timeout=60)
            report['final_resources']=resources(guest)
            guest.close();guest=None
            for name,wanted in expected.items():
                exported=args.artifacts/(name+'.guest.stdout');transfer(disk,'export','/out/'+name+'.stdout',exported)
                actual=exported.read_bytes()
                report['side_effects'][name]={'bytes':len(actual),'sha256':sha(exported),'expected_sha256':hashlib.sha256(wanted).hexdigest()}
                if actual!=wanted: raise AssertionError(f'{name}: complete stdout differs from host reference: {actual[:300]!r} != {wanted[:300]!r}')
            for name in ('depth_limit','fault_substitution'):
                exported=args.artifacts/(name+'.guest.stdout');transfer(disk,'export','/out/'+name+'.stdout',exported)
                actual=exported.read_bytes();code,body,markers,forbidden=GUEST_CASES[name]
                for marker in markers:
                    if marker not in actual: raise AssertionError(f'{name}: missing {marker!r} from saved stdout')
                for marker in forbidden:
                    if marker in actual: raise AssertionError(f'{name}: forbidden {marker!r} in saved stdout')
                report['side_effects'][name]={'stdout':actual.decode(errors='replace'),'sha256':sha(exported)}
            for name,wanted in (('child_marker',b'child_file\n'),('sub_marker',b'subshell_file\n'),('fork_shared.bin',b'abXdef'),('oom_parent.bin',b'beforeafter')):
                exported=args.artifacts/(name+'.guest');transfer(disk,'export','/out/'+name,exported)
                if exported.read_bytes()!=wanted: raise AssertionError('file side effect mismatch: '+name)
                report['side_effects'][name]={'bytes':len(wanted),'sha256':sha(exported)}
            report['checks'].append('all_stdout_and_file_side_effects_match_host_or_explicit_guest_contract')
            report['status']='passed'
    except Exception as error:
        report['error']=str(error)
        if guest: report['output_tail']=bytes(guest.output[-18000:]).decode(errors='replace')
        raise
    finally:
        if guest: guest.close()
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__': main()
