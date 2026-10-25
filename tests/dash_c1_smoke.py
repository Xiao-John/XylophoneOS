# SPDX-License-Identifier: Apache-2.0
"""Real XOS C1 pipelines; private disk, exact binary comparison, failure cleanup."""
import argparse
import hashlib
import json
import re
from pathlib import Path
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

COUNT = 131109


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_bytes(count):
    return bytes((i * 73 + (i >> 8) * 19 + 11) & 255 for i in range(count))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--dash-manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=ROOT/'build/dash_c1_report.json')
    parser.add_argument('--artifacts', type=Path, default=ROOT/'build/dash_c1_evidence')
    args = parser.parse_args()
    args.system = args.system.resolve()
    args.artifacts = args.artifacts/uuid.uuid4().hex
    args.artifacts.mkdir(parents=True, exist_ok=False)
    system = json.loads((args.system/'manifest.json').read_text())
    dash = json.loads(args.dash_manifest.read_text())
    report = {'status': 'failed', 'system_build_id': system['build_id'],
              'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'xos_sha256': sha(args.system/'xos.img'), 'dash_sha256': dash['sha256'],
              'sdk_manifest_sha256': sha(args.system/'sdk/manifest.json') if (args.system/'sdk/manifest.json').exists() else None,
              'checks': [], 'commands': [], 'host_reference': [], 'not_run': [
                  'unrelated_long_randomized_stress'], 'tools': {}}
    guest = None
    try:
        if report['xos_sha256'] != system['artifacts']['xos.img']['sha256']:
            raise AssertionError('system image does not match manifest')
        dash_elf = ROOT/dash['elf']
        if sha(dash_elf) != dash['sha256']:
            raise AssertionError('dash ELF does not match manifest')
        for name in ('x86_64-elf-gcc', 'nasm', 'clang'):
            path = shutil.which(name)
            report['tools'][name] = subprocess.check_output([path, '--version'], text=True).splitlines()[0] if path else 'not_found'
        with tempfile.TemporaryDirectory(prefix='xos_dash_c1_') as folder_name:
            folder = Path(folder_name)
            disk = folder/'work.img'
            probe = folder/'probe'
            source = ROOT/'tests/fixtures/dash_c1/pipe_probe.c'
            build_probe(source, probe, args.system/'sdk')
            report['probe_source_sha256'] = sha(source)
            report['probe_sha256'] = sha(probe)
            shutil.copy2(probe, args.artifacts/'pipe_probe.elf')
            create_fat32(disk, 512)
            for directory in ('/usr', '/usr/bin', '/tests', '/out', '/tmp'):
                transfer(disk, 'mkdir', directory)
            transfer(disk, 'import', '/usr/bin/dash', dash_elf)
            transfer(disk, 'import', '/out/probe', probe)
            scripts = {
                'binary': f'/out/probe generate {COUNT} | /out/probe copy | /out/probe copy | /out/probe collect {COUNT} /out/binary.bin\n',
                'early_producer': '/out/probe generate 127 | /out/probe expect 127\n',
                'empty_eof': '/out/probe generate 0 | /out/probe expect 0\n',
                'early_consumer': f'/out/probe generate {COUNT} | /out/probe early 17\n',
                'fault_first': '/out/probe fault | /out/probe expect 0\n',
                'fault_middle': f'/out/probe generate {COUNT} | /out/probe fault | /out/probe early 0\n',
                'last_status': '/out/probe exit 7 | /out/probe exit 23\n',
                'missing_first': '/missing/c1 | /out/probe spin\n',
                'missing_later': '/out/probe spin | /missing/c1\n',
                'too_long': '/out/probe spin | /out/probe copy | /out/probe copy | /out/probe copy | /out/probe copy\n',
                'closed_stdin': 'exec 0<&-; /out/probe generate 127 | /out/probe expect 127; printf "C1_CLOSED_STDIN_OK\\n"\n',
                'closed_stderr': 'exec 2>&-; /out/probe generate 127 | /out/probe expect 127; printf "C1_CLOSED_STDERR_OK\\n"\n',
                'redirect_override': '/out/probe generate 127 >/out/redirect.bin | /out/probe expect 0\n',
                'builtin_later': '/out/probe spin | printf SHOULD_NOT_RUN\n',
                'redirect_failure': '/out/probe spin | /out/probe copy >/missing/dir/file\nprintf "C1_REDIRECT_RECOVERED status=%s\\n" "$?"\n',
                'exhausted': '/out/probe spin | /out/probe copy | /out/probe copy | /out/probe copy\n',
            }
            report['scripts'] = {}
            for name, text in scripts.items():
                path = args.artifacts/(name+'.sh')
                path.write_text('# SPDX-License-Identifier: Apache-2.0\n'+text)
                transfer(disk, 'import', '/tests/'+name+'.sh', path)
                report['scripts'][name] = {'input': text, 'sha256': sha(path)}

            # Reference comparison uses a separately compiled native copy of the
            # same deterministic producer/consumer, never as kernel evidence.
            native = folder/'native_probe'
            subprocess.run([shutil.which('clang') or 'cc', '-O2', '-DXOS_REFERENCE', str(source), '-o', str(native)], check=True)
            report['host_reference_shell'] = '/bin/sh'
            for name in ('binary', 'early_producer', 'empty_eof', 'last_status'):
                text = scripts[name].replace('/out/probe', str(native)).replace('/out/binary.bin', str(folder/'reference.bin'))
                result = subprocess.run(['/bin/sh', '-c', text], capture_output=True, timeout=30)
                expected_code = 23 if name == 'last_status' else 0
                record = {'case': name, 'command': text, 'expected_code': expected_code,
                          'actual_code': result.returncode, 'stdout': result.stdout.decode(errors='replace'),
                          'stderr': result.stderr.decode(errors='replace')}
                report['host_reference'].append(record)
                if result.returncode != expected_code:
                    raise AssertionError('host reference failed: '+name)
            reference = (folder/'reference.bin').read_bytes()
            if reference != expected_bytes(COUNT):
                raise AssertionError('host reference byte mismatch')
            report['host_reference_binary_sha256'] = hashlib.sha256(reference).hexdigest()

            guest = Guest(args.system/'xos.img', 'dash_c1', work_disk=disk)
            report['qemu_command'] = guest.command
            report['tools']['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=40)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40)
            pump(guest, 1.5)
            baseline = resources(guest)
            report['baseline_resources'] = baseline

            def run(name, line, code, markers=(), timeout=90, baseline_override=None):
                record = {'name': name, 'line': line, 'expected_code': code,
                          'expected_markers': [m.decode(errors='replace') for m in markers], 'status': 'failed'}
                report['commands'].append(record)
                start = len(guest.output)
                try:
                    output = command(guest, line, f'kind=exited code={code}'.encode(), timeout=timeout)
                    for marker in markers:
                        if marker not in output:
                            raise AssertionError(f'{name}: missing {marker!r}')
                    current = resources(guest)
                    record.update(actual_resources=current, actual_code=code,
                                  output=output.decode(errors='replace'))
                    if current != (baseline_override or baseline):
                        raise AssertionError(f'{name}: leaked resources {current} baseline={baseline_override or baseline}')
                    record['status'] = 'passed'
                    report['checks'].append(name)
                    return output
                finally:
                    (args.artifacts/(name+'.serial.log')).write_bytes(bytes(guest.output[start:]))

            run('raw_pipe_permissions_readiness_short_io_and_slot_reuse', 'exec-file /out/probe raw', 0,
                (b'C1_RAW rounds=20',))
            output = run('four_stage_binary_stream_with_backpressure', 'dash /tests/binary.sh', 0,
                         (f'C1_CHECK bytes={COUNT}'.encode(), f'C1_GENERATED bytes={COUNT}'.encode()), 180)
            match = re.search(rb'short_writes=(\d+)', output)
            if not match or int(match.group(1)) == 0:
                raise AssertionError('large producer did not observe short writes/backpressure')
            report['producer_short_writes'] = int(match.group(1))
            run('producer_early_exit_drains_before_eof', 'dash /tests/early_producer.sh', 0,
                (b'C1_CHECK bytes=127', b'eof=1'))
            run('empty_producer_last_writer_eof', 'dash /tests/empty_eof.sh', 0,
                (b'C1_CHECK bytes=0', b'eof=1'))
            output = run('consumer_early_exit_wakes_broken_pipe_writer', 'dash /tests/early_consumer.sh', 0,
                         (b'C1_EARLY bytes=17', b'C1_WRITE_ERROR'))
            error = re.search(rb'C1_WRITE_ERROR errno=(\d+) EPIPE=(\d+)', output)
            if not error or error[1] != error[2]:
                raise AssertionError('producer failed without EPIPE')
            run('faulted_first_stage_delivers_eof', 'dash /tests/fault_first.sh', 0,
                (b'event=fault', b'C1_CHECK bytes=0'))
            run('faulted_middle_stage_releases_both_endpoints', 'dash /tests/fault_middle.sh', 0,
                (b'event=fault', b'C1_WRITE_ERROR'))
            run('pipeline_status_is_last_stage', 'dash /tests/last_status.sh', 23)
            run('missing_first_stage_fails_without_hanging_children', 'dash /tests/missing_first.sh', 127)
            run('missing_later_stage_cleans_started_sibling', 'dash /tests/missing_later.sh', 127)
            rejected = run('fifth_stage_rejected_before_any_start', 'dash /tests/too_long.sh', 2)
            # One start belongs to dash itself. Admission must reject before
            # starting any of the five requested external pipeline processes.
            if rejected.count(b'[process] event=started pid=') != 1 or b'C1_SPIN_READY' in rejected:
                raise AssertionError('over-limit pipeline started a child before admission failed')

            run('closed_parent_stdin_descriptor_restore', 'dash /tests/closed_stdin.sh', 0,
                (b'C1_CHECK bytes=127', b'C1_CLOSED_STDIN_OK'))
            run('closed_parent_stderr_descriptor_restore', 'dash /tests/closed_stderr.sh', 0,
                (b'C1_CHECK bytes=127', b'C1_CLOSED_STDERR_OK'))
            run('stage_redirection_overrides_pipe', 'dash /tests/redirect_override.sh', 0,
                (b'C1_CHECK bytes=0',))
            output = run('builtin_later_rejection_cleans_started_child', 'dash /tests/builtin_later.sh', 2)
            if b'SHOULD_NOT_RUN' in output: raise AssertionError('pipeline builtin executed')
            run('redirection_failure_cleans_children_and_shell_continues', 'dash /tests/redirect_failure.sh', 0,
                (b'C1_REDIRECT_RECOVERED status=2',))

            children = []
            for _ in range(2):
                out = command(guest, 'spawn-file /out/probe spin', b'[loader] started pid=', timeout=45)
                match = re.search(rb'\[loader\] started pid=(\d+)', out)
                if not match: raise AssertionError('missing background blocker PID')
                children.append(int(match[1]))
            occupied = resources(guest)
            if occupied[1] != baseline[1] + 2:
                raise AssertionError('resource exhaustion setup did not occupy two process slots')
            report['exhaustion_blockers'] = {'pids': children, 'resources': occupied}
            run('process_exhaustion_cleans_partial_pipeline', 'dash /tests/exhausted.sh', 126,
                baseline_override=occupied)
            for child in children:
                command(guest, f'kill {child}', b'kill: accepted')
                command(guest, f'wait {child}', b'kind=killed code=-9')
            if resources(guest) != baseline:
                raise AssertionError('resource exhaustion blocker cleanup leaked')

            interactive_start = len(guest.output)
            send_bytes(guest, b'dash -i\r')
            guest.expect(b'$ ', start=interactive_start, timeout=60)
            start = len(guest.output)
            send_bytes(guest, b'/out/probe input | /out/probe copy\r')
            guest.expect(b'C1_INPUT_READY', start=start, timeout=60)
            send_bytes(guest, b'c1_foreground_stdin_route\r')
            guest.expect(b'$ ', start=start, timeout=60)
            out = bytes(guest.output[start:])
            if b'c1_foreground_stdin_route' not in re.sub(rb'\[(?:process|task)\][^\r\n]*\r?\n', b'', out):
                raise AssertionError('first pipeline stage did not receive console stdin')
            report['commands'].append({'name': 'foreground_stdin_routes_to_first_stage', 'status': 'passed',
                                       'input': 'c1_foreground_stdin_route\\r', 'output': out.decode(errors='replace')})
            report['checks'].append('foreground_stdin_routes_to_first_stage')
            shell_pid = int(re.findall(rb'\[loader\] started pid=(\d+)', bytes(guest.output[interactive_start:]))[0])
            start = len(guest.output)
            send_bytes(guest, b'/out/probe spin | /out/probe copy | /out/probe copy\r')
            guest.expect(b'C1_SPIN_READY', start=start, timeout=60)
            send_bytes(guest, b'\x1b')
            guest.expect(b'$ ', start=start, timeout=60)
            cancelled = bytes(guest.output[start:])
            if b'cancelled_by_escape' not in cancelled:
                raise AssertionError('Escape did not cancel the foreground pipeline')
            start = len(guest.output)
            send_bytes(guest, b"printf 'C1_CANCEL_RECOVERED status=%d\\n' $?\r")
            guest.expect(b'$ ', start=start, timeout=30)
            recovered = bytes(guest.output[start:])
            if b'C1_CANCEL_RECOVERED status=137' not in recovered:
                raise AssertionError('pipeline cancellation status/recovery mismatch')
            report['commands'].append({'name': 'escape_cancels_group_and_recovers_shell', 'status': 'passed',
                'output': (cancelled+recovered).decode(errors='replace')})
            report['checks'].append('escape_during_pipeline_start_recovers_shell')
            start = len(guest.output)
            send_bytes(guest, b'/out/probe spin | /out/probe copy | /out/probe copy\r')
            guest.expect(f'event=wait_blocked parent={shell_pid} child='.encode(), start=start, timeout=60)
            send_bytes(guest, b'\x1b')
            guest.expect(b'$ ', start=start, timeout=60)
            if b'cancelled_by_escape pipeline_parent=' not in bytes(guest.output[start:]):
                raise AssertionError('fully launched pipeline was not group-cancelled')
            report['commands'].append({'name': 'escape_after_all_stages_blocked', 'status': 'passed',
                'output': bytes(guest.output[start:]).decode(errors='replace')})
            report['checks'].append('escape_after_all_stages_blocked')
            send_bytes(guest, b'exit\r')
            guest.expect_supervisor(start=start, timeout=60)
            pump(guest, 0.5)
            if resources(guest) != baseline:
                raise AssertionError('interactive stdin/cancellation leaked resources')
            report['checks'].append('escape_cancels_group_and_recovers_shell')
            # Repeat to catch cumulative endpoint/completion leaks and stale slots.
            for repeat in range(3):
                run(f'repeated_pipeline_slot_reuse_{repeat}', 'dash /tests/early_producer.sh', 0,
                    (b'C1_CHECK bytes=127',))
            command(guest, 'sync', b'[files] sync=ok', timeout=60)
            report['final_resources'] = resources(guest)
            guest.close()
            guest = None
            exported = args.artifacts/'binary.bin'
            transfer(disk, 'export', '/out/binary.bin', exported)
            actual = exported.read_bytes()
            report['guest_binary'] = {'bytes': len(actual), 'sha256': sha(exported),
                'expected_sha256': hashlib.sha256(expected_bytes(COUNT)).hexdigest()}
            if actual != expected_bytes(COUNT) or actual != reference:
                raise AssertionError('full guest output differs from every-byte expected or host reference')
            report['checks'].append('offline_export_full_binary_comparison_after_guest_sync')
            report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
        if guest is not None:
            report['output_tail'] = bytes(guest.output[-16000:]).decode(errors='replace')
        raise
    finally:
        if guest is not None: guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
