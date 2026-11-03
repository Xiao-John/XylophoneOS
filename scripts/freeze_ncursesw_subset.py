#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Freeze a source-bound ncursesw guest-tested subset, not full W1/W2."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from xos_app import tree_receipt

ROOT = Path(__file__).resolve().parents[1]
CHECKS = frozenset({
    'xsh_terminal_wide_input_output', 'xsh_split_utf8_and_window_bounds_local_refresh',
    'xsh_invalid_utf8_timeout_and_next_input_recovery',
    'xsh_split_combining_character_input',
    'xsh_missing_terminfo_failure_and_restoration',
    'xsh_terminal_reentry', 'xsh_terminal_locale', 'xsh_repeated_app_resource_baseline',
    'xsh_rejects_unmarked_terminal_program', 'xsh_faulted_app_detached_and_resources_recovered',
    'xsh_service_fault_recovery_and_new_application', 'xsh_restart_resource_baseline',
})
ARTIFACTS = {
    'wide_screen_probe.elf': 'wide_sha256', 'reentry_probe.elf': 'reentry_sha256',
    'wide_locale_probe.elf': 'locale_sha256', 'terminal_failure_probe.elf': 'failure_sha256',
    'terminal_crash_probe.elf': 'crash_sha256',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'candidate', 'consumers', 'sdk-candidate', 'ncurses-probe', 'terminfo', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    system, candidate, consumers, sdk_candidate, probe, terminfo = (p.resolve(strict=True) for p in
        (args.system, args.candidate, args.consumers, args.sdk_candidate, args.ncurses_probe, args.terminfo))
    output = args.output.resolve()
    require(output.is_relative_to(ROOT / 'build') and not output.exists() and
            not any(output.is_relative_to(p) for p in (system, candidate, consumers, sdk_candidate, probe, terminfo)),
            'output must be a new isolated build subdirectory')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip(),
            'commit all changes before freezing')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest_path = system / 'manifest.json'
    guest_path = system / 'ncurses_guest_probe_report.json'
    serial_path = system / 'ncurses_guest_serial.log'
    candidate_path = candidate / 'receipt.json'
    consumer_path = consumers / 'report.json'
    sdk_path = sdk_candidate / 'receipt.json'
    ncurses_path = probe / 'report.json'
    terminfo_path = terminfo / 'receipt.json'
    screen_path = system / 'ncurses_screen_report.json'
    screen_hardcopy = system / 'ncurses_screen_hardcopy.bin'
    screen_outer = system / 'ncurses_screen_outer_pty.bin'
    screen_probe = ROOT / 'tests/ncurses_screen_guest.py'
    manifest, guest, receipt, apps = (json.loads(p.read_text()) for p in
                                      (manifest_path, guest_path, candidate_path, consumer_path))
    require(screen_path.is_file() and screen_hardcopy.is_file() and screen_outer.is_file(),
            'host Screen evidence is missing')
    screen = json.loads(screen_path.read_text())
    require(screen.get('status') == 'passed_subset' and
            screen.get('profile') == 'GNU Screen attached 24x80, xterm serial subset' and
            {'screen_window_ascii_hardcopy', 'screen_outer_pty_cjk_and_combining_bytes'}.issubset(
                set(screen.get('checks', []))) and
            screen.get('guest_report_sha256') == sha(guest_path) and
            screen.get('serial_sha256') == sha(serial_path) and
            screen.get('probe_script_sha256') == sha(screen_probe) and
            screen.get('hardcopy_sha256') == sha(screen_hardcopy) and
            screen.get('outer_pty_sha256') == sha(screen_outer) and
            b'W2_LOCAL_CELL' in screen_hardcopy.read_bytes() and
            b'\xe4\xb8\xad' in screen_outer.read_bytes() and b'\xcc\x81' in screen_outer.read_bytes() and
            bool(screen.get('screen_version')) and bool(screen.get('screen_binary_sha256')),
            'host Screen evidence does not match')
    require(guest.get('status') == 'passed_probe' and guest.get('commit') == commit and
            guest.get('profile') == 'xsh-xterm-24x80-single' and
            CHECKS.issubset(set(guest.get('checks', []))), 'guest result does not meet the subset gate')
    require(not manifest.get('ncurses_supervisor_probe') and not manifest.get('terminal_supervisor_probe') and
            guest.get('build_id') == manifest.get('build_id') and
            guest.get('system_manifest_sha256') == sha(manifest_path) and
            guest.get('system_sha256') == sha(system / 'xos-install.iso') and
            guest.get('terminal_sha256') == sha(system / 'user_terminal.image.elf') and
            manifest['artifacts']['xos-install.iso']['sha256'] == guest.get('system_sha256') and
            manifest['artifacts']['user_terminal.image.elf']['sha256'] == guest.get('terminal_sha256') and
            guest.get('serial_sha256') == sha(serial_path) and
            guest.get('probe_source_sha256') == sha(ROOT / 'tests/ncurses_guest_probe.py'),
            'system or guest evidence does not match')
    for sources in (manifest['sources'], apps['source_sha256']):
        for name, digest in sources.items():
            path = ROOT / name
            require(path.is_file() and sha(path) == digest, 'source differs: ' + name)
    files = {}
    for path in sorted(candidate.rglob('*')):
        require(not path.is_symlink(), 'candidate symlinks are unsupported')
        if path.is_file() and path != candidate_path:
            files[path.relative_to(candidate).as_posix()] = sha(path)
    digest = hashlib.sha256((json.dumps(files, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()).hexdigest()
    require(receipt.get('status') == 'built_unverified' and files == receipt.get('files') and
            digest == receipt.get('tree_sha256') == guest.get('composed_sdk_tree_sha256') and
            guest.get('composed_receipt_sha256') == sha(candidate_path) and
            guest.get('consumers_report_sha256') == sha(consumer_path) and
            guest.get('sdk_receipt_sha256') == sha(sdk_path) and
            guest.get('ncurses_report_sha256') == sha(ncurses_path) and
            guest.get('terminfo_receipt_sha256') == sha(terminfo_path) and
            receipt.get('target_report_sha256') == sha(ncurses_path) and
            receipt.get('terminfo_receipt_sha256') == sha(terminfo_path) and
            apps.get('candidate_tree_sha256') == digest and apps.get('status') == 'cross_linked_guest_not_run' and
            guest.get('ncurses_sha256') == sha(candidate / 'sdk/lib/libncursesw.a') and
            guest.get('terminfo_sha256') == sha(candidate / 'target/usr/local/share/terminfo/x/xterm'),
            'candidate or consumer evidence does not match')
    for name, field in ARTIFACTS.items():
        require(sha(consumers / name) == apps['artifacts'].get(name) == guest.get(field),
                'consumer artifact differs: ' + name)

    output.mkdir(parents=True)
    shutil.copytree(candidate, output / 'delivery')
    evidence = output / 'evidence'
    evidence.mkdir()
    for source, name in ((manifest_path, 'system_manifest.json'), (guest_path, 'guest_report.json'),
                         (serial_path, 'serial.log'), (consumer_path, 'consumers_report.json'),
                         (sdk_path, 'sdk_receipt.json'), (ncurses_path, 'ncurses_report.json'),
                         (terminfo_path, 'terminfo_receipt.json'),
                         (screen_path, 'screen_report.json'), (screen_hardcopy, 'screen_hardcopy.bin'),
                         (screen_outer, 'screen_outer_pty.bin'),
                         (system / 'xos-install.iso', 'xos-install.iso'),
                         (system / 'user_terminal.image.elf', 'terminal.elf')):
        shutil.copyfile(source, evidence / name)
    for name in ARTIFACTS:
        shutil.copyfile(consumers / name, evidence / name)
    # Recheck mutable inputs after copying; never bind a changed candidate or log.
    copied = output / 'delivery'
    require(all(sha(copied / name) == value for name, value in receipt['files'].items()) and
            sha(copied / 'receipt.json') == sha(candidate_path) and
            sha(evidence / 'system_manifest.json') == guest['system_manifest_sha256'] and
            sha(evidence / 'consumers_report.json') == guest['consumers_report_sha256'] and
            sha(evidence / 'sdk_receipt.json') == guest['sdk_receipt_sha256'] and
            sha(evidence / 'ncurses_report.json') == guest['ncurses_report_sha256'] and
            sha(evidence / 'terminfo_receipt.json') == guest['terminfo_receipt_sha256'] and
            sha(evidence / 'screen_report.json') == sha(screen_path) and
            sha(evidence / 'screen_hardcopy.bin') == screen['hardcopy_sha256'] and
            sha(evidence / 'screen_outer_pty.bin') == screen['outer_pty_sha256'] and
            sha(evidence / 'xos-install.iso') == guest['system_sha256'] and
            sha(evidence / 'terminal.elf') == guest['terminal_sha256'] and
            all(sha(evidence / name) == guest[field] for name, field in ARTIFACTS.items()) and
            sha(evidence / 'serial.log') == guest['serial_sha256'] and
            sha(evidence / 'guest_report.json') == sha(guest_path), 'inputs changed during freeze')
    tree_hash, output_files = tree_receipt(output)
    result = {'status': 'guest_verified_subset', 'scope': 'xsh xterm 24x80 single-thread ncursesw',
              'not_accepted': ['full_w1', 'full_w2', 'other_terminals', 'dynamic_resize',
                               'threaded_profile', 'member_license_review'],
              'commit': commit, 'system_build_id': manifest['build_id'],
              'candidate_tree_sha256': digest, 'guest_report_sha256': sha(guest_path),
              'tree_sha256': tree_hash, 'files': output_files}
    (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'tree_sha256': tree_hash, 'files': len(output_files)}, indent=2))


if __name__ == '__main__':
    main()
