#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the flat, path-safe SSG-P4A evidence report."""
import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def copy_bytes(source, output, name):
    source = Path(source)
    if not source.is_file():
        raise SystemExit('missing evidence input: ' + source.name)
    (output / name).write_bytes(source.read_bytes())


def copy_json(source, output, name):
    data = json.loads(Path(source).read_text())
    (output / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def copy_log(source, output, name):
    data = Path(source).read_bytes()
    (output / name).write_bytes(gzip.compress(data, compresslevel=9, mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--initial-validation', type=Path, required=True)
    parser.add_argument('--state-initial', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--system-build', type=Path, required=True)
    parser.add_argument('--sdk-overlay', type=Path, required=True)
    parser.add_argument('--report-name', required=True, help='new report name below docs/reports/')
    parser.add_argument('--refresh', action='store_true',
                        help='refresh generated leaves in an existing compliant report directory')
    args = parser.parse_args()
    report_name = args.report_name
    if not re.fullmatch(r'[a-z][a-z0-9_]+', report_name) or report_name == 'ssg_p4a_subscriber_20261104':
        parser.error('use a new report name; the historical P4A report is frozen')
    validation, initial = [path.resolve(strict=True) for path in (args.validation, args.initial_validation)]
    state_initial = args.state_initial.resolve(strict=True)
    build, system, sdk_overlay = [path.resolve(strict=True) for path in
                                  (args.build, args.system_build, args.sdk_overlay)]
    final_summary = json.loads((validation / 'summary.json').read_text())
    if (final_summary.get('status') != 'PASSED_SCOPED' or
        final_summary.get('stress', {}).get('passed_runs') != 12 or
        final_summary.get('stress', {}).get('requested_runs') != 12):
        raise SystemExit('final validation summary is not complete or has failed scenarios')
    system_manifest = json.loads((system / 'manifest.json').read_text())
    build_manifest = json.loads((build / 'manifest.json').read_text())
    if build_manifest.get('status') != 'BUILT':
        raise SystemExit('P4A build manifest is not BUILT')
    if build_manifest.get('base_commit') != final_summary.get('base_commit'):
        raise SystemExit('P4A build and validation base commits differ')
    if system_manifest.get('build_id') != final_summary.get('system_build_id'):
        raise SystemExit('P4A system build does not match validation summary')
    output = root / 'docs/reports' / report_name
    if output.exists():
        if not args.refresh or not (output / 'manifest.json').is_file():
            existing = sorted(path.name for path in output.iterdir())
            if existing != ['README.md']:
                raise SystemExit('report directory already has evidence; use --refresh only for generated leaves')
    else:
        output.mkdir(parents=True)

    copy_bytes(validation / 'summary.json', output, 'validation_summary.json')
    copy_bytes(initial / 'summary.json', output, 'validation_initial_attempt.json')
    copy_bytes(build / 'manifest.json', output, 'p4a_build_manifest.json')
    copy_bytes(sdk_overlay / 'p4a_overlay_receipt.json', output, 'sdk_overlay_receipt.json')

    artifact_names = ('kernel.elf', 'kernel.bin', 'xos-install.iso')
    artifacts = {}
    for name in artifact_names:
        item = system_manifest['artifacts'][name]
        if sha_bytes((system / name).read_bytes()) != item['sha256']:
            raise SystemExit('system artifact changed: ' + name)
        artifacts[name] = {'bytes': item['bytes'], 'sha256': item['sha256']}
    system_summary = {
        'status': 'BUILT',
        'base_commit': final_summary['base_commit'],
        'build_id': system_manifest['build_id'],
        'version': system_manifest['version'],
        'source_digest': system_manifest['source_sha256'],
        'toolchain': system_manifest['toolchain'],
        'tool_versions': {name: system_manifest['tools'].get(name) for name in ('gcc', 'g++', 'target', 'ld', 'nasm')},
        'kernel_layout': system_manifest['kernel_layout'],
        'artifacts': artifacts,
    }
    (output / 'system_build_summary.json').write_text(json.dumps(system_summary, indent=2) + '\n')

    for name in ('browser', 'browser-test', 'notes', 'notes-test'):
        if name.startswith('browser'):
            candidates = [build / name / 'browser.portable.receipt.json']
        else:
            candidates = [build / name / 'notes.receipt.json']
        source = next((path for path in candidates if path.is_file()), None)
        if source is not None:
            copy_bytes(source, output, name.replace('-', '_') + '_build_receipt.json')

    copy_bytes(root / 'tests/fixtures/ssg_browser/p2f.html', output, 'input_browser_p2f.html')
    copy_bytes(validation / 'scenarios/first/synthetic.txt', output, 'input_synthetic_notes.txt')
    copy_bytes(root / 'tests/ssg_p4a_host_test.py', output, 'host_reference_test.py')
    copy_bytes(validation / 'host_reference.log', output, 'host_reference.log')
    copy_bytes(root / 'tests/ssg_p4a_verify.py', output, 'independent_frame_verifier.py')
    copy_bytes(root / 'tests/ssg_p4a_resync_verify.py', output, 'independent_resync_verifier.py')
    copy_bytes(root / 'tests/ssg_p4a_state_guest.py', output, 'subscriber_state_guest_runner.py')
    copy_bytes(root / 'tests/ssg_p4a_name_check.py', output, 'c30_spdx_name_check.py')
    copy_bytes(root / 'build/p4a-name-spdx-check.json', output, 'c30_spdx_name_check.json')
    copy_bytes(root / 'tests/ssg_p4a_guest.py', output, 'p4a_guest_runner.py')
    copy_bytes(root / 'scripts/run_ssg_p4a_validation.py', output, 'validation_runner.py')
    copy_bytes(root / 'scripts/build_ssg_p4a.py', output, 'p4a_build_runner.py')
    copy_bytes(root / 'scripts/prepare_ssg_p4a_toolchain.py', output, 'toolchain_overlay_runner.py')
    copy_bytes(root / 'scripts/export_ssg_p4a_report.py', output, 'report_exporter.py')

    scenario_names = tuple(json.loads((validation / 'summary.json').read_text())['scenario_runs'][:14][i]['scenario']
                           for i in range(14))
    for name in scenario_names:
        source_dir = validation / 'scenarios' / name
        copy_bytes(source_dir / 'report.json', output, name + '_report.json')
        copy_bytes(source_dir / 'independent_check.json', output, name + '_independent_check.json')
        copy_log(source_dir / 'serial.log', output, name + '_serial.log.gz')

    for fault in ('corrupt-frame', 'backpressure'):
        source_dir = validation / 'resync' / (fault + '-new-baseline')
        prefix = 'resync_' + fault.replace('-', '_')
        copy_bytes(source_dir / 'report.json', output, prefix + '_baseline_report.json')
        copy_bytes(source_dir / 'independent_check.json', output, prefix + '_baseline_independent_check.json')
        copy_bytes(source_dir / 'resync-independent-check.json', output, prefix + '_independent_check.json')
        copy_log(source_dir / 'serial.log', output, prefix + '_baseline_serial.log.gz')

    for index in range(1, 13):
        name = f'run-{index:02d}'
        source_dir = validation / 'stress' / name
        prefix = 'stress_' + f'{index:02d}'
        copy_bytes(source_dir / 'report.json', output, prefix + '_report.json')
        copy_bytes(source_dir / 'independent_check.json', output, prefix + '_independent_check.json')
        copy_log(source_dir / 'serial.log', output, prefix + '_serial.log.gz')

    state_dir = validation / 'subscriber-state'
    copy_bytes(state_dir / 'report.json', output, 'subscriber_state_guest_report.json')
    copy_log(state_dir / 'serial.log', output, 'subscriber_state_guest_serial.log.gz')
    contract_dir = validation / 'p3c-contract'
    copy_bytes(contract_dir / 'report.json', output, 'p3c_contract_report.json')
    copy_log(contract_dir / 'serial.log', output, 'p3c_contract_serial.log.gz')
    ordinary_dir = validation / 'p3c-ordinary'
    copy_bytes(ordinary_dir / 'report.json', output, 'p3c_console_watch_report.json')
    copy_bytes(ordinary_dir / 'ordinary-check.json', output, 'p3c_console_watch_independent_check.json')
    copy_log(ordinary_dir / 'serial.log', output, 'p3c_console_watch_serial.log.gz')

    copy_bytes(initial / 'scenarios/duplicate-ack/report.json', output,
               'duplicate_ack_initial_harness_failure.json')
    copy_log(initial / 'scenarios/duplicate-ack/serial.log', output,
             'duplicate_ack_initial_harness_failure_serial.log.gz')
    final_duplicate = validation / 'scenarios/duplicate-ack'
    copy_bytes(final_duplicate / 'report.json', output, 'duplicate_ack_final_validation_report.json')
    copy_bytes(final_duplicate / 'independent_check.json', output,
               'duplicate_ack_final_validation_independent_check.json')
    copy_log(final_duplicate / 'serial.log', output, 'duplicate_ack_final_validation_serial.log.gz')
    followup = root / 'build/p4a-final-evidence/duplicate-ack-rerun-02'
    copy_bytes(followup / 'report.json', output, 'duplicate_ack_corrected_rerun_report.json')
    copy_bytes(followup / 'independent_check.json', output, 'duplicate_ack_corrected_rerun_independent_check.json')
    copy_log(followup / 'serial.log', output, 'duplicate_ack_corrected_rerun_serial.log.gz')
    copy_bytes(state_initial / 'report.json', output, 'state_guest_initial_harness_failure.json')
    copy_log(state_initial / 'serial.log', output, 'state_guest_initial_harness_failure_serial.log.gz')

    iteration_notes = {
        'initial_attempts_preserved': [
            {'case': 'current-main C30 compatibility build', 'result': 'FAILED',
             'cause': 'P3C Watch retained the old Baseline/Diff type spellings after the upstream C30 rename',
             'resolution': 'updated Watch adapter and supervisor references to baseline and baseline_diff_result'},
            {'case': 'Notes cross-build with the previously built Qt E17 SDK', 'result': 'FAILED',
             'cause': 'that SDK header still declared file::Client while current main uses file::client',
             'resolution': 'created an isolated derived SDK overlay with the current-main file_client object; no external Qt build was modified'},
            {'case': 'first QEMU boot of the new optical image', 'result': 'FAILED',
             'cause': 'the Guest helper treated the .iso as a floppy and produced no serial output',
             'resolution': 'Guest runner now selects CD boot for .iso images'},
            {'case': 'first ACK route', 'result': 'FAILED',
             'cause': 'Qt startup diagnostic text on stderr was written into the ACK Pipe',
             'resolution': 'ACK uses stdout fd 1; diagnostics remain on stderr fd 2; the Subscriber does not start a Qt application object'},
            {'case': 'initial full-Pipe timing calibration', 'result': 'WOULD_BLOCK observed but ACK arrived before deadline',
             'resolution': 'test pause extended to ten seconds; final run shows the Supervisor timeout and UNKNOWN'},
            {'case': 'first Subscriber state test', 'result': 'state assertions passed but the Guest wrapper matched a different summary phrase',
             'resolution': 'corrected the summary pattern; final state Guest test passes 25 checks'},
            {'case': 'first thread/page return assertion', 'result': 'FAILED',
             'cause': 'the live Supervisor allocator retained a per-process high-water allocation during the watch',
             'resolution': 'report in-process page deltas and verify global counters after Supervisor exit'},
            {'case': 'first duplicate-ACK harness attempt', 'result': 'FAILED_TEST_EXPECTATION',
             'cause': 'the Subscriber successfully wrote a duplicate ACK before the Supervisor rejected its stale sequence',
             'resolution': 'corrected the Guest assertion; the corrected duplicate-ACK rerun and final validation both pass'},
            {'case': 'host independent verifier after C30 variable normalization', 'result': 'FAILED_VERIFIER_EXCEPTION',
             'cause': 'the normalized frame_header_size constant was shadowed by a decoded header local',
             'resolution': 'renamed the decoded field and reran every saved scenario, resync, and stress frame audit; all pass'},
            {'case': 'upstream main advanced during the long run', 'result': 'SYNCED',
             'cause': 'main advanced from 6fe330c to 071330f3 with release-preparation changes',
             'resolution': 'merged latest main without touching P4A runtime sources and boot-tested the post-sync system image'},
            {'case': 'repo-wide docs consistency after main 071 sync', 'result': 'FAILED_THEN_RESOLVED',
             'cause': 'docs/releases/next_release.md has two links to docs/releases/playbook.md, which is absent from upstream main',
             'resolution': 'upstream 59ac60db added the linked playbook; reran docs_consistency on latest main and it passed'},
        ],
        'failed_attempts_are_retained': True,
        'no_failure_logs_were_deleted': True,
    }
    (output / 'test_iteration_notes.json').write_text(json.dumps(iteration_notes, indent=2) + '\n')

    files = {}
    for path in sorted(output.iterdir()):
        if path.name == 'manifest.json':
            continue
        if not path.is_file() or path.is_symlink():
            raise SystemExit('report root must remain flat and symlink-free')
        files[path.name] = sha_bytes(path.read_bytes())
    (output / 'manifest.json').write_text(json.dumps({'version': 1, 'files': files}, indent=2) + '\n')
    print('exported', report_name, 'files=', len(files), 'manifest_sha256=', sha_bytes((output / 'manifest.json').read_bytes()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
