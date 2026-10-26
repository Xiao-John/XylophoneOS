# SPDX-License-Identifier: Apache-2.0
"""Actual XOS exec identity, image replacement, all-FD inheritance and rollback."""
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
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''): value.update(chunk)
    return value.hexdigest()


def exec_opt_in(path):
    """Inspect the actual ELF opt-in, including its read-only load mapping."""
    data = Path(path).read_bytes()
    if data[:6] != b'\x7fELF\x02\x01': raise AssertionError('expected ELF64 little endian probe')
    shoff = struct.unpack_from('<Q',data,40)[0]
    shsize,shcount,strings_index = struct.unpack_from('<HHH',data,58)
    sections = [struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*shsize) for i in range(shcount)]
    names_header = sections[strings_index]
    names = data[names_header[4]:names_header[4]+names_header[5]]
    for section in sections:
        name = names[section[0]:].split(b'\0',1)[0]
        if name != b'.xos.exec': continue
        if section[1]!=1 or section[2]&3!=2 or section[5]!=16:
            raise AssertionError('exec marker must be 16-byte read-only ALLOC PROGBITS')
        marker = data[section[4]:section[4]+section[5]]
        if struct.unpack('<QII',marker)!=(0x3349424143455858,3,16):
            raise AssertionError('unexpected exec ABI marker contents')
        phoff = struct.unpack_from('<Q',data,32)[0]
        phsize,phcount = struct.unpack_from('<HH',data,54)
        for index in range(phcount):
            ph = struct.unpack_from('<IIQQQQQQ',data,phoff+index*phsize)
            if ph[0]==1 and ph[1]&6==4 and ph[3]<=section[3] and section[3]+16<=ph[3]+ph[5] and ph[2]+section[3]-ph[3]==section[4]:
                return {'section':'.xos.exec','address':section[3],'offset':section[4],
                        'flags':section[2],'load_flags':ph[1],'sha256':hashlib.sha256(marker).hexdigest(),
                        'magic':'0x3349424143455858','version':3,'size':16}
        raise AssertionError('exec marker lacks a matching read-only file-backed LOAD')
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--threading-sdk', type=Path)
    parser.add_argument('--only-oom', action='store_true')
    parser.add_argument('--skip-oom', action='store_true')
    parser.add_argument('--report', type=Path, default=ROOT/'build/dash_c3_exec_report.json')
    parser.add_argument('--artifacts', type=Path, default=ROOT/'build/dash_c3_exec_evidence')
    args = parser.parse_args()
    if args.only_oom and args.skip_oom: parser.error('--only-oom and --skip-oom are mutually exclusive')
    args.system = args.system.resolve()
    run_id = uuid.uuid4().hex
    args.artifacts = args.artifacts.resolve()/run_id
    args.artifacts.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'phase': 'C3 exec', 'run_id': run_id, 'artifacts': str(args.artifacts),
              'source_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
              'sources': {}, 'tools': {}, 'build_commands': [], 'commands': [], 'checks': [],
              'side_effects': {}, 'only_oom': args.only_oom, 'skip_oom': args.skip_oom,
              'not_run': ['SMP', 'asynchronous_POSIX_signals', 'long_randomized_stress']}
    guest = None
    try:
        system_path = args.system/'manifest.json'
        system = json.loads(system_path.read_text())
        sdk = args.system/'sdk'
        sdk_receipt = json.loads((sdk/'manifest.json').read_text())
        image = args.system/'xos.img'
        report.update(system_build_id=system['build_id'], system_manifest_sha256=sha(system_path),
                      xos_sha256=sha(image), sdk_manifest_sha256=sha(sdk/'manifest.json'))
        if report['xos_sha256'] != system['artifacts']['xos.img']['sha256']:
            raise AssertionError('system image does not match manifest')
        if sdk_receipt['build_id'] != system['build_id']:
            raise AssertionError('kernel and SDK build IDs differ')
        fixtures = ROOT/'tests/fixtures/dash_c3_exec'
        for source in [Path(__file__).resolve(), *sorted(fixtures.iterdir()),
                       ROOT/'src/kernel/arch/x86_64/tasks.cpp', ROOT/'src/user/libc/newlib_syscalls.cpp',
                       ROOT/'src/user/loader/load.cpp', ROOT/'src/shared/include/xos/process_abi.hpp']:
            if source.is_file(): report['sources'][str(source.relative_to(ROOT))] = sha(source)
        saved_fixtures = args.artifacts/'fixture_sources'
        saved_fixtures.mkdir()
        for source in sorted(fixtures.iterdir()):
            if source.is_file():
                saved = saved_fixtures/source.name;shutil.copy2(source,saved)
                if sha(saved)!=report['sources'][str(source.relative_to(ROOT))]:
                    raise AssertionError('fixture changed while capturing source snapshot: '+source.name)
        shutil.copy2(Path(__file__).resolve(),args.artifacts/'runner_snapshot.py')
        cc = shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc'
        cxx = shutil.which('x86_64-elf-g++') or 'x86_64-elf-g++'
        tools = ROOT/'build/target_tools'
        objcopy = shutil.which('x86_64-elf-objcopy') or 'x86_64-elf-objcopy'
        for name, tool in [('gcc',Path(cc)), ('g++',Path(cxx)), ('as',tools/'as'), ('ld',tools/'ld'),('objcopy',Path(objcopy))]:
            tool = Path(shutil.which(str(tool)) or tool)
            report['tools'][name] = {'path': str(tool.resolve()), 'sha256': sha(tool),
                'version': subprocess.check_output([str(tool),'--version'], text=True).splitlines()[0]}
        base_libgcc = Path(subprocess.check_output([cc,'-print-libgcc-file-name'], text=True).strip())
        report['base_libgcc_sha256'] = sha(base_libgcc)
        report['sdk_inputs'] = {str(path.relative_to(sdk)):sha(path) for path in (
            sdk/'crt0_posix.o',sdk/'user.ld',sdk/'lib/libxos.a',sdk/'lib/libxos_loader.a',
            sdk/'lib/libc.a',sdk/'lib/libm.a',sdk/'include/xos/process_abi.hpp',sdk/'include/xos/spawn.hpp')}

        def run_build(line, label):
            line = [str(item) for item in line]
            report['build_commands'].append(line)
            result = subprocess.run(line, capture_output=True, text=True)
            (args.artifacts/(label+'.log')).write_text(result.stdout+result.stderr)
            if result.returncode: raise AssertionError(f'{label} failed: {result.returncode}')

        def linker(profile, label):
            text = (profile/'user.ld').read_text()
            start = text.index('PHDRS')
            end = text.index('}',start)
            text = text[:end]+'    probe PT_LOAD FLAGS(6);\n'+text[end:]
            text = text.replace('/DISCARD/', '.exec_probe_slot 0x5fc00000 : { KEEP(*(.exec_probe_slot)) } :probe\n    /DISCARD/',1)
            path = args.artifacts/(label+'.ld');path.write_text(text);return path

        single_linker = linker(sdk,'single_probe')

        def compile_probe(name, source, defines=(), profile=sdk, threaded=False):
            obj, elf = args.artifacts/(name+'.o'), args.artifacts/(name+'.elf')
            flags = ['-B'+str(tools)+'/', '-std=gnu11','-O2','-g','-mno-red-zone',
                     '-fno-pie','-fno-pic','-fno-stack-protector','-ftls-model=local-exec',
                     '-I'+str(profile/'include'), *defines]
            run_build([cc,*flags,'-c',source,'-o',obj],name+'_compile')
            if threaded:
                libraries = ['-Wl,--whole-archive',profile/'lib/libxos.a','-Wl,--no-whole-archive',
                             profile/'cpp/lib/libstdc++.a',profile/'cpp/lib/libsupc++.a',
                             profile/'lib/libc.a',profile/'lib/libm.a',profile/'cpp/lib/libgcc.a']
                script = linker(profile,'threaded_probe')
            else:
                libraries = [profile/'lib/libxos.a',profile/'lib/libxos_loader.a',
                             profile/'lib/libc.a',profile/'lib/libm.a',base_libgcc]
                script = single_linker
            run_build([cxx if threaded else cc,'-B'+str(tools)+'/','-nostdlib','-static','-no-pie',
                       '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
                       '-T',script,profile/'crt0_posix.o',obj,'-Wl,--start-group',*libraries,
                       '-Wl,--end-group','-o',elf],name+'_link')
            report.setdefault('probes',{})[name] = {'sha256':sha(elf),'bytes':elf.stat().st_size,
                                                   'object_sha256':sha(obj),'path':str(elf)}
            if not threaded:
                marker = exec_opt_in(elf)
                if marker is None: raise AssertionError('new CRT probe lacks exec v3 opt-in: '+name)
                report['probes'][name]['exec_abi_marker'] = marker
            return elf

        source_elf = compile_probe('source',saved_fixtures/'source.c')
        target_elf = compile_probe('target',saved_fixtures/'target.c')
        if sha(source_elf) == sha(target_elf): raise AssertionError('source and target must be different ELFs')
        legacy = args.artifacts/'legacy_target.elf'
        run_build([objcopy,'--remove-section=.xos.exec',target_elf,legacy],'legacy_remove_marker')
        if exec_opt_in(legacy) is not None: raise AssertionError('legacy negative fixture still advertises exec v3')
        report['legacy_fixture'] = {'path':str(legacy),'sha256':sha(legacy),'derived_from_sha256':sha(target_elf),
            'transformation':'objcopy --remove-section=.xos.exec; current target code with exec opt-in removed',
            'scope':'unmarked ABI admission negative fixture; not a published legacy binary qualification'}
        huge = None if args.skip_oom else compile_probe('huge_target',saved_fixtures/'target.c',['-DC3_HUGE_TARGET'])
        threaded = None
        if args.threading_sdk and not args.only_oom:
            profile = args.threading_sdk.resolve()
            receipt_path = profile/'manifest.json';receipt = json.loads(receipt_path.read_text())
            for path,digest in receipt['artifacts'].items():
                if sha(profile/path) != digest: raise AssertionError('threaded SDK artifact mismatch: '+path)
            for path,digest in receipt['inputs'].items():
                if sha(ROOT/path) != digest: raise AssertionError('threaded SDK input mismatch: '+path)
            report['threading_sdk_manifest_sha256'] = sha(receipt_path)
            threaded = compile_probe('threaded_source',saved_fixtures/'source.c',['-DXOS_THREADED_RUNTIME'],profile,True)
        else:
            report['not_run'].append('threaded_SDK_exec_ENOTSUP' if not args.only_oom else 'normal_exec_cases_in_only_oom_run')
        if args.skip_oom: report['not_run'].append('partial_mapping_ENOMEM_rollback')

        with tempfile.TemporaryDirectory(prefix='xos_c3_exec_') as folder_name:
            folder = Path(folder_name);disk = folder/'work.img';private = folder/'boot.img'
            shutil.copyfile(image,private);create_fat32(disk,512)
            for directory in ('/tests','/out','/tmp','/tmp/work','/tests/path-invalid','/tests/path-legacy','/tests/path-good'): transfer(disk,'mkdir',directory)
            transfer(disk,'import','/tests/source',source_elf);transfer(disk,'import','/tests/target',target_elf)
            invalid = args.artifacts/'invalid.elf';invalid.write_bytes(b'not an ELF\x00c3-exec-negative\n')
            transfer(disk,'import','/tests/invalid',invalid)
            transfer(disk,'import','/tests/legacy-target',legacy)
            transfer(disk,'import','/tests/path-invalid/candidate',invalid)
            transfer(disk,'import','/tests/path-legacy/candidate',legacy)
            transfer(disk,'import','/tests/path-good/candidate',target_elf)
            report['execvp_candidates'] = {'invalid_first_sha256':sha(invalid),'unmarked_first_sha256':sha(legacy),
                'second_valid_sha256':sha(target_elf),'command':'execvp(candidate, valid_target_arguments)',
                'expected':'first candidate ENOEXEC/ENOTSUP returns without executing the second candidate'}
            if huge: transfer(disk,'import','/tests/huge-target',huge)
            if threaded: transfer(disk,'import','/tests/threaded',threaded)
            guest = Guest(private,'dash_c3_exec_'+run_id[:12],work_disk=disk)
            report['qemu_command'] = guest.command
            qemu = Path(guest.command[0]);report['tools']['qemu'] = {'path':str(qemu.resolve()),'sha256':sha(qemu),
                'version':subprocess.check_output([str(qemu),'--version'],text=True).splitlines()[0]}
            guest.expect(b'xos64> ',timeout=40);send_bytes(guest,b'run\r')
            guest.expect_supervisor(trace=True,timeout=40);pump(guest,1.5)
            baseline = resources(guest);report['baseline_resources'] = baseline
            selected = [('oom','exec-driver',0)] if args.only_oom else [
                ('execve','exec-file',37),('execv','exec-file',37),('execvp','exec-file',37),
                ('_execve','exec-file',37),('authority','exec-driver',37),('long_arg','exec-file',37),
                ('missing','exec-file',0),('invalid','exec-file',0),('legacy','exec-file',0),
                ('path_invalid','exec-file',0),('path_legacy','exec-file',0),
                ('raw','exec-file',0),('quota','exec-driver',0)]
            if not args.only_oom and not args.skip_oom: selected.append(('oom','exec-driver',0))
            expected_side_effects = {}
            for mode, launcher, expected in selected:
                line = f'{launcher} /tests/source {mode}'
                record = {'mode':mode,'line':line,'expected_code':expected,'status':'failed'}
                report['commands'].append(record);start = len(guest.output)
                try:
                    output = command(guest,line,b'kind=exited code=',timeout=1200 if mode=='oom' else 180)
                    record['output'] = output.decode(errors='replace')
                    if b'C3_EXEC_FAIL ' in output or b'C3_EXEC_UNREACHABLE_AFTER_SUCCESS' in output or b'C3_EXEC_HUGE_UNEXPECTEDLY_STARTED' in output:
                        raise AssertionError('guest probe failed: '+mode)
                    waits = re.findall(rb'\[wait\] pid=(\d+) kind=exited code=(-?\d+)',output)
                    if len(waits)!=1 or int(waits[0][1])!=expected: raise AssertionError('wrong supervisor completion: '+mode)
                    source = re.search(rb'C3_EXEC_SOURCE pid=(\d+) tid=(\d+) heap=(\d+) mode=',output)
                    if not source or int(waits[0][0])!=int(source[1]): raise AssertionError('parent did not wait on original PID')
                    record['source_pid'],record['source_tid'] = int(source[1]),int(source[2])
                    if expected==37:
                        if mode=='long_arg' and (b'C3_EXEC_LONG_ARGUMENT bytes=1024 exact_bytes=ok PASS' not in output or b'C3_EXEC_SPAWN_ARG_LIMIT E2BIG PASS' not in output):
                            raise AssertionError('long exec argument or unchanged ordinary-spawn limit failed')
                        target = re.search(rb'C3_EXEC_TARGET pid=(\d+) tid=(\d+).* PASS',output)
                        replacement = re.search(rb'event=exec_replaced old_pid=(\d+) current_pid=(\d+) target_pid=(\d+) staging_pid=(\d+) tid=(\d+) old_address_space=(0x[0-9a-f]+) address_space=(0x[0-9a-f]+) file_session_rekeyed=1',output)
                        if not target or not replacement: raise AssertionError('missing exec identity/rekey trace')
                        if [int(target[1]),int(target[2])] != [int(source[1]),int(source[2])]: raise AssertionError('exec changed PID/TID')
                        if any(int(replacement[i])!=int(source[1]) for i in (1,2,3)) or int(replacement[5])!=int(source[2]): raise AssertionError('trace identity mismatch')
                        if replacement[6]==replacement[7] or int(replacement[4])==int(source[1]): raise AssertionError('address space/staging replacement missing')
                        retired = re.search(rb'event=reclaimed pid='+replacement[4]+rb' pages=(\d+)',output)
                        if not retired or int(retired[1])<36: raise AssertionError('old image was not reclaimed')
                        record['replacement'] = {'staging_pid':int(replacement[4]),'old_cr3':replacement[6].decode(),
                            'new_cr3':replacement[7].decode(),'reclaimed_pages':int(retired[1]),'session_rekeyed':True}
                        expected_side_effects[mode+'-stream.dat'] = b'0123XY6789'
                        expected_side_effects[mode+'-combined.log'] = b'stdout-target\nstderr-target\n'
                        expected_side_effects[mode+'-only-clo.dat'] = b'before'
                    else:
                        marker = b'C3_EXEC_RAW ' if mode=='raw' else b'C3_EXEC_FAILURE mode='+mode.encode()
                        if marker not in output or b'event=exec_replaced' in output: raise AssertionError('negative exec did not preserve old image')
                        counters = []
                        for label, fields in re.findall(rb'C3_EXEC_RESOURCES (\S+) ([^\r\n]+)',output):
                            counters.append({'phase':label.decode(),**{key.decode():int(value) for key,value in re.findall(rb'(\w+)=(\d+)',fields)}})
                        record['guest_resource_counters'] = counters
                        if len(counters)!=2 or {k:v for k,v in counters[0].items() if k!='phase'}!={k:v for k,v in counters[1].items() if k!='phase'}:
                            raise AssertionError('failed exec resource counters differ')
                        if mode=='oom':
                            stages = re.findall(rb'event=exec_prepared pid=\d+ staging_pid=(\d+)',output)
                            reclaimed = [int(m[1]) for stage in stages for m in re.findall(rb'event=reclaimed pid=('+stage+rb') pages=(\d+)',output)]
                            if not reclaimed or max(reclaimed)<200*256: raise AssertionError('ENOMEM did not follow real partial mapping of >200MiB')
                            record['partial_mapping_reclaimed_pages'] = max(reclaimed)
                        expected_side_effects[mode+'-stream.dat'] = b'0123456789'
                        expected_side_effects[mode+'-combined.log'] = b''
                        expected_side_effects[mode+'-only-clo.dat'] = b'before-after'
                    current = resources(guest);record['resources_after'] = current
                    if current!=baseline: raise AssertionError(f'{mode}: resources {current} != {baseline}')
                    record.update(status='passed',actual_code=expected)
                    report['checks'].append(mode)
                finally:
                    log = args.artifacts/(mode+'.serial.log');log.write_bytes(bytes(guest.output[start:]))
                    record['serial_log'] = {'path':str(log),'sha256':sha(log)}
            if threaded:
                start = len(guest.output)
                output = command(guest,'exec-file /tests/threaded',b'kind=exited code=',timeout=120)
                (args.artifacts/'threaded.serial.log').write_bytes(output)
                if b'C3_EXEC_THREADED ENOTSUP unchanged_fd PASS' not in output or b'kind=exited code=0' not in output:
                    raise AssertionError('threaded SDK did not explicitly reject exec')
                if resources(guest)!=baseline: raise AssertionError('threaded rejection leaked resources')
                report['checks'].append('threaded_profile_ENOTSUP_unchanged_fd')
                report['commands'].append({'mode':'threaded','line':'exec-file /tests/threaded','status':'passed',
                    'actual_code':0,'output':output.decode(errors='replace'),'resources_after':baseline})
            command(guest,'sync',b'[files] sync=ok',timeout=60)
            report['final_resources'] = resources(guest)
            serial = args.artifacts/'all.serial.log';serial.write_bytes(bytes(guest.output))
            report['serial_log'] = {'path':str(serial),'sha256':sha(serial)}
            guest.close();guest=None
            for name, expected in expected_side_effects.items():
                exported = args.artifacts/name;transfer(disk,'export','/out/'+name,exported)
                actual = exported.read_bytes()
                report['side_effects'][name] = {'sha256':sha(exported),'bytes':len(actual),
                    'expected_sha256':hashlib.sha256(expected).hexdigest(),'expected_bytes':expected.decode()}
                if actual!=expected: raise AssertionError('guest side effect byte mismatch: '+name)
            report['checks'].append('offline_full_byte_side_effect_comparison_after_guest_sync')
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        if guest is not None: report['output_tail'] = bytes(guest.output[-20000:]).decode(errors='replace')
        raise
    finally:
        if guest is not None:
            serial = args.artifacts/'all.serial.log';serial.write_bytes(bytes(guest.output))
            report['serial_log'] = {'path':str(serial),'sha256':sha(serial)}
            guest.close()
        receipt = json.dumps(report,indent=2)+'\n'
        (args.artifacts/'report.json').write_text(receipt)
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(receipt)
    print(json.dumps(report))


if __name__=='__main__': main()
