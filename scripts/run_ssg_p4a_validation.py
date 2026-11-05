#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run P4A Guest scenarios, independent frame audits, P3C regression, and stress."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))
from ssg_public_paths import portable

scenarios = ('first', 'notes-edit', 'browser-scroll', 'notes-revoke',
             'protect-document', 'protect-ancestor', 'browser-exit', 'notes-exit',
             'stop', 'cancel-inflight', 'wrong-ack', 'duplicate-ack',
             'corrupt-frame', 'backpressure')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_logged(name, command, env, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as log:
        result = subprocess.run(command, cwd=root, env=env, stdout=log,
                                stderr=subprocess.STDOUT, check=False)
    return result.returncode


def portable_command(command, mappings):
    return portable([str(item) for item in command], mappings, strict=True)


def run_guest_case(case, run_dir, image, supervisor, browser, notes, subscriber,
                   html, python, qemu, mappings):
    command = [python, root / 'tests/ssg_p4a_guest.py', '--image', image,
               '--supervisor', supervisor, '--browser', browser, '--notes', notes,
               '--subscriber', subscriber, '--input', html, '--case', case,
               '--output', run_dir]
    environment = dict(os.environ)
    environment['QEMU'] = str(qemu)
    guest_log = run_dir.parent / (run_dir.name + '.guest.log')
    guest_status = run_logged(case, command, environment, guest_log)
    guest_report_path = run_dir / 'report.json'
    guest_report = json.loads(guest_report_path.read_text()) if guest_report_path.exists() else {}
    verify_status = 99
    verify_log = run_dir.parent / (run_dir.name + '.verify.log')
    if guest_status == 0:
        verify_status = run_logged(case + '-independent',
            [python, root / 'tests/ssg_p4a_verify.py', run_dir], environment, verify_log)
    serial_path = run_dir / 'serial.log'
    serial = serial_path.read_bytes() if serial_path.exists() else b''
    event_count = len(re.findall(rb'^P4A_TX_BEGIN stream=', serial, re.MULTILINE))
    ack_count = len(re.findall(rb'^P4A_ACK stream=\d+ status=COMMITTED', serial, re.MULTILINE))
    reset_count = len(re.findall(rb'^P4A_SUBSCRIBER_RESET_REQUIRED ', serial, re.MULTILINE))
    timeout_count = len(re.findall(rb'TIMEOUT|delivery=UNKNOWN', serial))
    subscriber_exit = next((line.decode() for line in serial.splitlines()
                            if line.startswith(b'P4A_SUBSCRIBER_EXIT ')), None)
    stop_line = next((line.decode() for line in serial.splitlines()
                      if line.startswith(b'P4A_WATCH_STOP ')), None)
    result = {
        'scenario': case,
        'status': 'PASSED_SCOPED' if guest_status == 0 and verify_status == 0 else 'FAILED',
        'guest_exit_code': guest_status,
        'independent_verify_exit_code': verify_status,
        'events_attempted': event_count,
        'supervisor_acks': ack_count,
        'reset_count': reset_count,
        'timeout_or_unknown_count': timeout_count,
        'subscriber_exit': subscriber_exit,
        'watch_stop': stop_line,
        'supervisor_exit': guest_report.get('supervisor_exit'),
        'runtime_seconds': guest_report.get('elapsed_seconds'),
        'resource_samples': {'before': guest_report.get('before'), 'after': guest_report.get('after'),
                             'thread_stats': guest_report.get('thread_stats'),
                             'pipe_capacity_available': guest_report.get('pipe_capacity_available')},
        'resources_restored': guest_report.get('resources_restored'),
        'source_exits': guest_report.get('source_exits', []),
        'input_hashes': guest_report.get('inputs', {}),
        'guest_log': portable(str(guest_log), mappings, strict=True),
        'verify_log': portable(str(verify_log), mappings, strict=True),
        'command_template': portable_command(command, mappings),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--p4a-build', type=Path, required=True)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=12)
    parser.add_argument('--skip-p3c-regression', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 24:
        parser.error('--repetitions must be between 1 and 24')
    system = args.system_build.resolve(strict=True)
    build = args.p4a_build.resolve(strict=True)
    qemu = args.qemu.resolve(strict=True)
    output = args.output.resolve()
    if root / 'build' not in output.parents or output.exists():
        parser.error('choose a new output directory under build/')
    output.mkdir(parents=True)
    python = sys.executable
    image = system / 'xos.iso'
    floppy = system / 'xos.img'
    supervisor = build / 'supervisor-test/supervisor-test.elf'
    browser = build / 'browser-test/browser.elf'
    notes = build / 'notes-test/notes.elf'
    subscriber = build / 'subscriber/subscriber.elf'
    html = root / 'tests/fixtures/ssg_browser/p2f.html'
    mappings = [('XOS_SYSTEM_BUILD_DIR', system), ('XOS_P4A_BUILD_DIR', build),
                ('XOS_VALIDATION_OUT', output), ('XOS_IMAGE', image),
                ('XOS_FLOPPY_IMAGE', floppy), ('XOS_QEMU', qemu),
                ('XOS_PYTHON', python), ('XOS_INPUT', html)]
    for path in (image, floppy, supervisor, browser, notes, subscriber, html):
        if not path.is_file():
            raise SystemExit('missing validation input: ' + path.name)

    environment = dict(os.environ)
    environment['QEMU'] = str(qemu)
    host_log = output / 'host_reference.log'
    host_status = run_logged('host-reference', [python, root / 'tests/ssg_p4a_host_test.py'],
                             environment, host_log)
    if host_status != 0:
        raise SystemExit('host reference checks failed; see host_reference.log')

    results = []
    by_name = {}
    scenarios = list(scenarios)
    for scenario in scenarios:
        run_dir = output / 'scenarios' / scenario
        result = run_guest_case(scenario, run_dir, image, supervisor, browser, notes,
                                subscriber, html, python, qemu, mappings)
        results.append(result);by_name[scenario]=run_dir
        print('scenario', scenario, result['status'], flush=True)

    resync_results = []
    for failure_name in ('corrupt-frame', 'backpressure'):
        resync_name = failure_name + '-new-baseline'
        run_dir = output / 'resync' / resync_name
        fresh = run_guest_case('first', run_dir, image, supervisor, browser, notes,
                               subscriber, html, python, qemu, mappings)
        results.append(fresh);by_name[resync_name]=run_dir
        verify_log = output / 'resync' / (failure_name + '.verify.log')
        resync_status = run_logged(failure_name + '-resync',
            [python, root / 'tests/ssg_p4a_resync_verify.py', by_name[failure_name], run_dir],
            environment, verify_log)
        resync_results.append({'failure_scenario': failure_name,
                               'status': 'PASSED_SCOPED' if resync_status == 0 else 'FAILED',
                               'independent_verify_exit_code': resync_status,
                               'verify_log': portable(str(verify_log), mappings, strict=True)})
        print('resync', failure_name, resync_results[-1]['status'], flush=True)

    stress_runs = []
    for index in range(1, args.repetitions + 1):
        name = f'run-{index:02d}'
        run_dir = output / 'stress' / name
        result = run_guest_case('first', run_dir, image, supervisor, browser, notes,
                               subscriber, html, python, qemu, mappings)
        result['run_id'] = name
        stress_runs.append(result)
        print('stress', name, result['status'], flush=True)

    state_output = output / 'subscriber-state'
    state_command = [python, root / 'tests/ssg_p4a_state_guest.py', '--image', floppy,
                     '--payload', build / 'subscriber-state-test/subscriber-state-test.elf',
                     '--output', state_output]
    state_log = output / 'subscriber-state.guest.log'
    state_status = run_logged('subscriber-state', state_command, environment, state_log)
    state_report = json.loads((state_output / 'report.json').read_text()) if (state_output / 'report.json').exists() else {}
    state_result = {'status': 'PASSED_SCOPED' if state_status == 0 else 'FAILED',
                    'guest_exit_code': state_status, 'report': state_report,
                    'log': portable(str(state_log), mappings, strict=True),
                    'command_template': portable_command(state_command, mappings)}

    contract_output = output / 'p3c-contract'
    contract_command = [python, root / 'tests/ssg_watch_contract_guest.py', '--image', floppy,
                        '--payload', build / 'contract-test/contract-test.elf', '--output', contract_output]
    contract_log = output / 'p3c-contract.guest.log'
    contract_status = run_logged('p3c-contract', contract_command, environment, contract_log)
    contract_report = json.loads((contract_output / 'report.json').read_text()) if (contract_output / 'report.json').exists() else {}
    p3c_contract = {'status': contract_report.get('status', 'FAILED'), 'guest_exit_code': contract_status,
                    'report': contract_report, 'log': portable(str(contract_log), mappings, strict=True),
                    'command_template': portable_command(contract_command, mappings)}

    p3c_ordinary = {'status': 'NOT_RUN'}
    if not args.skip_p3c_regression:
        ordinary_output = output / 'p3c-ordinary'
        ordinary_command = [python, root / 'tests/ssg_watch_guest.py', '--image', floppy,
                            '--supervisor', build / 'supervisor/supervisor.elf',
                            '--browser', build / 'browser/browser.elf', '--notes', build / 'notes/notes.elf',
                            '--browser-receipt', build / 'browser/browser.portable.receipt.json',
                            '--input', root / 'tests/fixtures/ssg_browser/p2f.html',
                            '--ordinary', '--output', ordinary_output]
        ordinary_log = output / 'p3c-ordinary.guest.log'
        ordinary_status = run_logged('p3c-ordinary', ordinary_command, environment, ordinary_log)
        ordinary_verify_log = output / 'p3c-ordinary.verify.log'
        ordinary_verify_status = 99
        if ordinary_status == 0:
            ordinary_verify_status = run_logged('p3c-ordinary-independent',
                [python, root / 'tests/ssg_watch_nondiagnostic_verify.py', ordinary_output,
                 '--require-structured'], environment, ordinary_verify_log)
        p3c_ordinary = {'status': 'PASSED_SCOPED' if ordinary_status == 0 and ordinary_verify_status == 0 else 'FAILED',
                        'guest_exit_code': ordinary_status,
                        'independent_verify_exit_code': ordinary_verify_status,
                        'report': json.loads((ordinary_output / 'report.json').read_text())
                                  if (ordinary_output / 'report.json').exists() else {},
                        'guest_log': portable(str(ordinary_log), mappings, strict=True),
                        'verify_log': portable(str(ordinary_verify_log), mappings, strict=True),
                        'command_template': portable_command(ordinary_command, mappings)}

    stress_passed = sum(item['status'] == 'PASSED_SCOPED' for item in stress_runs)
    scenario_passed = sum(item['status'] == 'PASSED_SCOPED' for item in results[:len(scenarios)])
    resync_passed = sum(item['status'] == 'PASSED_SCOPED' for item in resync_results)
    complete = (host_status == 0 and scenario_passed == len(scenarios) and
                resync_passed == len(resync_results) and stress_passed == args.repetitions and
                state_result['status'] == 'PASSED_SCOPED' and p3c_contract['status'] == 'PASSED_SCOPED' and
                p3c_ordinary['status'] in ('PASSED_SCOPED', 'NOT_RUN'))
    summary = {
        'status': 'PASSED_SCOPED' if complete else 'PARTIAL',
        'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'system_build_id': json.loads((system / 'manifest.json').read_text())['build_id'],
        'p4a_build_status': json.loads((build / 'manifest.json').read_text())['status'],
        'host_reference': {'status': 'PASSED_SCOPED' if host_status == 0 else 'FAILED',
                           'log': portable(str(host_log), mappings, strict=True)},
        'scenario_runs': results,
        'resync_runs': resync_results,
        'stress': {'status': 'PASSED_SCOPED' if stress_passed == args.repetitions else 'PARTIAL',
                   'requested_runs': args.repetitions, 'passed_runs': stress_passed,
                   'runs': stress_runs, 'retry_policy': 'all attempts retained; no failure runs removed'},
        'subscriber_state_guest': state_result,
        'p3c_contract': p3c_contract,
        'p3c_console_compatibility': p3c_ordinary,
        'pipe_resource_scope': 'before/after available-object sample plus four-object reuse/stale-token probe; no exact global counter syscall',
        'exit_race_root_cause': 'UNRESOLVED',
        'globalAtomicSnapshot': 'NOT_IMPLEMENTED',
        'production_broker': 'NOT_IMPLEMENTED',
        'localpilot_end_to_end': 'NOT_RUN',
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('P4A_VALIDATION', summary['status'], 'stress=', f'{stress_passed}/{args.repetitions}', flush=True)
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
