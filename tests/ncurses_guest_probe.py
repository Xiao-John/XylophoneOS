# SPDX-License-Identifier: Apache-2.0
"""Run isolated ncurses and locale probes after committing all changes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import send_bytes
from work_disk import transfer
from xos_app import tree_receipt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'sdk-candidate', 'ncurses-probe', 'consumers', 'terminfo'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--xsh', action='store_true', help='exercise tty-run in the normal supervisor')
    parser.add_argument('--composed', type=Path, help='verify consumers linked against this composed SDK candidate')
    args = parser.parse_args()
    system, candidate, probe, consumers, terminfo = [p.resolve(strict=True) for p in
        (args.system, args.sdk_candidate, args.ncurses_probe, args.consumers, args.terminfo)]
    if ROOT / 'build' not in system.parents:
        parser.error('system must be an isolated build subdirectory')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise SystemExit('commit all changes before running the guest probe')
    manifest = json.loads((system / 'manifest.json').read_text())
    sdk_receipt = json.loads((candidate / 'receipt.json').read_text())
    target = json.loads((probe / 'report.json').read_text())
    apps = json.loads((consumers / 'report.json').read_text())
    term = json.loads((terminfo / 'receipt.json').read_text())
    composed = args.composed.resolve(strict=True) if args.composed else None
    composed_receipt = json.loads((composed / 'receipt.json').read_text()) if composed else None
    lock_path = ROOT / 'src/ports/ncurses/source_lock.json'
    source_lock = json.loads(lock_path.read_text())
    if args.xsh and (manifest.get('ncurses_supervisor_probe') or manifest.get('terminal_supervisor_probe')):
        raise SystemExit('xsh requires a normal supervisor build')
    if not args.xsh and not manifest.get('ncurses_supervisor_probe'):
        raise SystemExit('system was not built with --ncurses-supervisor-probe')
    for sources in (manifest['sources'], sdk_receipt['inputs'], apps['source_sha256']):
        for name, expected in sources.items():
            source = ROOT / name
            if not source.is_file() or sha(source) != expected:
                raise SystemExit(f'source differs from recorded build: {name}')
    if (sdk_receipt.get('status') != 'built_unverified' or
        tree_receipt(candidate / 'sdk')[0] != sdk_receipt.get('sdk_tree_sha256') or
        target.get('sdk_tree_sha256') != sdk_receipt.get('sdk_tree_sha256') or
        target.get('archive_valid') is not True or apps.get('status') != 'cross_linked_guest_not_run' or
        (not composed and (apps.get('sdk_tree_sha256') != sdk_receipt.get('sdk_tree_sha256') or
                           apps.get('probe_report_sha256') != sha(probe / 'report.json'))) or
        term.get('status') != 'built_guest_not_run' or
        target.get('source_sha256') != source_lock['archive_sha256'] or
        term.get('source_sha256') != source_lock['archive_sha256'] or
        term.get('source_lock_sha256') != sha(lock_path) or
        term.get('target_report_sha256') != sha(probe / 'report.json') or
        term.get('target_config_sha256') != sha(probe / 'build/include/ncurses_cfg.h') or
        term.get('target_library_sha256') != target.get('archive_sha256') or
        (not composed and apps.get('ncurses_archive_sha256') != target.get('archive_sha256')) or
        sha(probe / 'build/lib/libncursesw.a') != target.get('archive_sha256')):
        raise SystemExit('SDK, ncurses, consumer and terminfo receipts do not match')
    if composed:
        files = {p.relative_to(composed).as_posix(): sha(p) for p in sorted(composed.rglob('*'))
                 if p.is_file() and p != composed / 'receipt.json'}
        digest = hashlib.sha256((json.dumps(files, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()).hexdigest()
        if (any(p.is_symlink() for p in composed.rglob('*')) or
            composed_receipt.get('status') != 'built_unverified' or files != composed_receipt.get('files') or
            digest != composed_receipt.get('tree_sha256') or apps.get('candidate_tree_sha256') != digest or
            composed_receipt.get('base_sdk_tree_sha256') != sdk_receipt['sdk_tree_sha256'] or
            composed_receipt.get('target_report_sha256') != sha(probe / 'report.json') or
            composed_receipt.get('terminfo_receipt_sha256') != sha(terminfo / 'receipt.json')):
            raise SystemExit('composed SDK and consumer receipts do not match')
    image, terminal, legacy = (system / name for name in
                               ('xos-install.iso', 'user_terminal.image.elf', 'user_hello.image.elf'))
    for path in (image, terminal, legacy):
        if manifest['artifacts'].get(path.name, {}).get('sha256') != sha(path):
            raise SystemExit(f'system artifact differs from manifest: {path.name}')
    wide, reentry, locale, failure, crash = (consumers / name for name in
        ('wide_screen_probe.elf', 'reentry_probe.elf', 'wide_locale_probe.elf', 'terminal_failure_probe.elf',
         'terminal_crash_probe.elf'))
    for path in (wide, reentry, locale, failure, crash):
        if apps['artifacts'].get(path.name) != sha(path):
            raise SystemExit(f'consumer differs from receipt: {path.name}')
    entry = (composed / 'target/usr/local/share/terminfo/x/xterm' if composed
             else terminfo / 'terminfo' / term['entry'])
    if term['entry'] != 'x/xterm' or not entry.is_file() or entry.is_symlink() or sha(entry) != term['entry_sha256']:
        raise SystemExit('terminfo data differs from receipt')
    report = {'status': 'failed', 'scope': 'bounded ncurses and locale probes, not full W1/W2 acceptance',
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'profile': 'xsh-xterm-24x80-single' if args.xsh else 'test-supervisor-xterm-24x80-single',
              'system_manifest_sha256': sha(system / 'manifest.json'),
              'sdk_receipt_sha256': sha(candidate / 'receipt.json'),
              'ncurses_report_sha256': sha(probe / 'report.json'),
              'consumers_report_sha256': sha(consumers / 'report.json'),
              'terminfo_receipt_sha256': sha(terminfo / 'receipt.json'),
              'probe_source_sha256': sha(Path(__file__).resolve()),
              'build_id': manifest['build_id'], 'system_sha256': sha(image), 'terminal_sha256': sha(terminal),
              'sdk_tree_sha256': sdk_receipt['sdk_tree_sha256'], 'ncurses_sha256': target['archive_sha256'],
              'terminfo_sha256': sha(entry), 'wide_sha256': sha(wide), 'reentry_sha256': sha(reentry),
              'locale_sha256': sha(locale), 'failure_sha256': sha(failure), 'crash_sha256': sha(crash),
              'legacy_sha256': sha(legacy), 'checks': []}
    if composed:
        report['composed_sdk_tree_sha256'] = composed_receipt['tree_sha256']
        report['composed_receipt_sha256'] = sha(composed / 'receipt.json')
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_ncurses_probe_') as folder:
            disk = Path(folder) / 'work.img'
            create_fat32(disk, 512)
            for path in ('/bin', '/usr', '/usr/local', '/usr/local/share', '/usr/local/share/terminfo',
                         '/usr/local/share/terminfo/x'):
                transfer(disk, 'mkdir', path)
            for destination, source in (('/bin/terminal.elf', terminal), ('/bin/wide.elf', wide),
                                        ('/bin/reentry.elf', reentry), ('/bin/locale.elf', locale),
                                        ('/bin/failure.elf', failure), ('/bin/crash.elf', crash),
                                        ('/bin/legacy.elf', legacy),
                                        ('/usr/local/share/terminfo/x/xterm', entry)):
                transfer(disk, 'import', destination, source)
            guest = Guest(image, 'ncurses_guest_probe', work_disk=disk, iso=True)
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            if args.xsh:
                guest.expect(b'xsh> ', timeout=45)
                start = len(guest.output)
                send_bytes(guest, b'trace on\r')
                guest.expect(b'xsh: trace on', start=start, timeout=30)
                guest.expect(b'xsh> ', start=start, timeout=30)
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/wide.elf\r')
                guest.expect(b'W2_INPUT_READY', start=start, timeout=60)
                screen = bytes(guest.output[start:])
                if (b'\xe4\xb8\xad\xcc\x81' not in screen or b'W2_LOCAL_CELL' not in screen or
                        not re.search(rb'\x1b\[[0-9;]*31(?:;[0-9]*)?m', screen)):
                    raise AssertionError('xsh wide screen output missing')
                send_bytes(guest, b'\x1bOD')
                guest.expect(b'W2_UTF8_READY', start=start, timeout=30)
                send_bytes(guest, b'\xe4')
                time.sleep(0.05)
                send_bytes(guest, b'\xb8\xad\x1bOP')
                guest.expect(b'W2_INVALID_READY', start=start, timeout=30)
                send_bytes(guest, b'\xffA')
                guest.expect(b'W2_INVALID_RECOVERY_READY', start=start, timeout=30)
                send_bytes(guest, b'B')
                guest.expect(b'W2_COMBINING_READY', start=start, timeout=30)
                send_bytes(guest, b'a\xcc')
                time.sleep(0.05)
                send_bytes(guest, b'\x81')
                guest.expect(b' kind=exited code=0', start=start, timeout=60)
                marker = guest.output.find(b' kind=exited code=0', start)
                guest.expect(b'xsh> ', start=marker + len(b' kind=exited code=0'), timeout=60)
                if any(s in bytes(guest.output[start:]) for s in (b'program exited with status', b'xsh: cannot')):
                    raise AssertionError('xsh wide consumer failed')
                report['checks'].append('xsh_terminal_wide_input_output')
                report['checks'].append('xsh_split_utf8_and_window_bounds_local_refresh')
                report['checks'].append('xsh_invalid_utf8_timeout_and_next_input_recovery')
                report['checks'].append('xsh_split_combining_character_input')

                def resources():
                    start = len(guest.output)
                    send_bytes(guest, b'stats\r')
                    guest.expect(b'[resources] free=', start=start, timeout=30)
                    guest.expect(b'xsh> ', start=start, timeout=30)
                    match = re.search(rb'\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)',
                                      bytes(guest.output[start:]))
                    if not match:
                        raise AssertionError('incomplete resource report')
                    return tuple(map(int, match.groups()))

                baseline = resources()
                report['resources_after_wide'] = baseline
                for program in ('reentry', 'locale'):
                    start = len(guest.output)
                    send_bytes(guest, ('tty-run /bin/' + program + '.elf\r').encode())
                    guest.expect(b' kind=exited code=0', start=start, timeout=60)
                    marker = guest.output.find(b' kind=exited code=0', start)
                    guest.expect(b'xsh> ', start=marker + len(b' kind=exited code=0'), timeout=60)
                    if any(s in bytes(guest.output[start:]) for s in (b'program exited with status', b'xsh: cannot')):
                        raise AssertionError('xsh ' + program + ' consumer failed')
                    report['checks'].append('xsh_terminal_' + program)
                after_apps = resources()
                report['resources_after_apps'] = after_apps
                if after_apps != baseline:
                    raise AssertionError(f'resource mismatch after apps: {baseline} -> {after_apps}')
                report['checks'].append('xsh_repeated_app_resource_baseline')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/legacy.elf\r')
                guest.expect(b'xsh: cannot validate executable:', start=start, timeout=30)
                guest.expect(b'error=-18', start=start, timeout=30)
                guest.expect(b'xsh> ', start=start, timeout=30)
                report['checks'].append('xsh_rejects_unmarked_terminal_program')
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/crash.elf\r')
                guest.expect(b'W1_CRASH_READY', start=start, timeout=60)
                guest.expect(b' kind=faulted', start=start, timeout=60)
                guest.expect(b' vector=14', start=start, timeout=60)
                marker = guest.output.find(b' vector=14', start)
                guest.expect(b'xsh> ', start=marker + len(b' vector=14'), timeout=60)
                if resources() != baseline:
                    raise AssertionError('resource mismatch after terminal application fault')
                report['checks'].append('xsh_faulted_app_detached_and_resources_recovered')
                start = len(guest.output)
                send_bytes(guest, b'ps\r')
                guest.expect(b'xsh> ', start=start, timeout=30)
                processes = bytes(guest.output[start:])
                match = re.search(rb'pid=(\d+) name=/bin/termin\s', processes)
                if not match:
                    raise AssertionError('terminal service not found in xsh process list')
                start = len(guest.output)
                send_bytes(guest, b'kill ' + match.group(1) + b'\r')
                guest.expect(b'xsh: terminal service restarted; input discarded', start=start, timeout=60)
                marker = guest.output.find(b'input discarded', start)
                guest.expect(b'xsh> ', start=marker, timeout=30)
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/locale.elf\r')
                guest.expect(b' kind=exited code=0', start=start, timeout=60)
                marker = guest.output.find(b' kind=exited code=0', start)
                guest.expect(b'xsh> ', start=marker + len(b' kind=exited code=0'), timeout=60)
                report['checks'].append('xsh_service_fault_recovery_and_new_application')
                after_restart = resources()
                report['resources_after_restart'] = after_restart
                if after_restart != baseline:
                    raise AssertionError(f'resource mismatch after restart: {baseline} -> {after_restart}')
                report['checks'].append('xsh_restart_resource_baseline')
                # Move the actual xterm entry aside in this private test disk;
                # unlike an unknown TERM name this tests an absent database
                # for the otherwise supported profile.
                term_path = '/usr/local/share/terminfo/x/xterm'
                saved_path = '/usr/local/share/terminfo/x/xterm.bak'
                start = len(guest.output)
                send_bytes(guest, f'mv {term_path} {saved_path}\r'.encode())
                guest.expect(b'[files] renamed', start=start, timeout=30)
                guest.expect(b'xsh> ', start=start, timeout=30)
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/reentry.elf\r')
                guest.expect(b' kind=exited code=2', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                if resources() != baseline:
                    raise AssertionError('resource mismatch after missing terminfo failure')
                start = len(guest.output)
                send_bytes(guest, f'mv {saved_path} {term_path}\r'.encode())
                guest.expect(b'[files] renamed', start=start, timeout=30)
                guest.expect(b'xsh> ', start=start, timeout=30)
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/reentry.elf\r')
                guest.expect(b' kind=exited code=0', start=start, timeout=60)
                guest.expect(b'xsh> ', start=start, timeout=60)
                if resources() != baseline:
                    raise AssertionError('resource mismatch after terminfo restoration')
                report['checks'].append('xsh_missing_terminfo_failure_and_restoration')
                report['status'] = 'passed_probe'
                return
            guest.expect(b'W2_BOOT_READY', timeout=45)
            send_bytes(guest, b'!')
            guest.expect(b'W2_SERVICE_READY', timeout=45)
            marker = guest.expect_any((b'W2_INPUT_READY', b'W2_WIDE_FAILED'), timeout=60)
            if marker != b'W2_INPUT_READY':
                raise AssertionError('wide consumer failed before input')
            screen = bytes(guest.output)
            if b'\xe4\xb8\xad\xcc\x81' not in screen or not re.search(rb'\x1b\[[0-9;]*31(?:;[0-9]*)?m', screen):
                raise AssertionError('combined wide output or red foreground escape missing')
            send_bytes(guest, b'\x1bOD')
            guest.expect(b'W2_UTF8_READY', timeout=30)
            send_bytes(guest, b'\xe4')
            time.sleep(0.05)
            send_bytes(guest, b'\xb8\xad\x1bOP')
            guest.expect(b'W2_INVALID_READY', timeout=30)
            send_bytes(guest, b'\xffA')
            guest.expect(b'W2_INVALID_RECOVERY_READY', timeout=30)
            send_bytes(guest, b'B')
            guest.expect(b'W2_COMBINING_READY', timeout=30)
            send_bytes(guest, b'a\xcc')
            time.sleep(0.05)
            send_bytes(guest, b'\x81')
            marker = guest.expect_any((b'W2_WIDE_OK', b'W2_WIDE_FAILED'), timeout=60)
            if marker != b'W2_WIDE_OK':
                raise AssertionError('wide consumer returned failure')
            report['checks'].append('wide_window_color_combining_timeout_left_f1_cjk')
            report['checks'].append('invalid_utf8_timeout_and_next_input_recovery')
            report['checks'].append('split_combining_character_input')
            marker = guest.expect_any((b'W2_REENTRY_OK', b'W2_REENTRY_FAILED'), timeout=60)
            if marker != b'W2_REENTRY_OK':
                raise AssertionError('reentry consumer returned failure')
            report['checks'].append('unknown_terminal_size_and_reentry')
            marker = guest.expect_any((b'W2_LOCALE_OK', b'W2_LOCALE_FAILED'), timeout=60)
            if marker != b'W2_LOCALE_OK':
                raise AssertionError('locale consumer returned failure')
            report['checks'].append('locale_utf8_fragment_invalid_width_and_roundtrip')
            guest.expect(b'W2_RECOVER_OK', timeout=60)
            marker = guest.expect_any((b'W2_RECOVER_APP_OK', b'W2_RECOVER_APP_FAILED'), timeout=60)
            if marker != b'W2_RECOVER_APP_OK':
                raise AssertionError('locale consumer failed after terminal restart')
            report['checks'].append('terminal_kill_reauthorize_and_new_app')
            guest.expect(b'W1_FAULT_APP_READY', timeout=60)
            guest.expect(b'W2_FAULT_APP_RECOVER_OK', timeout=60)
            report['checks'].append('parent_child_terminal_error_on_service_death_and_recovery')
            report['status'] = 'passed_probe'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            report['serial_sha256'] = hashlib.sha256(guest.output).hexdigest()
            (system / 'ncurses_guest_serial.log').write_bytes(guest.output)
            guest.close()
        (system / 'ncurses_guest_probe_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"PASS {len(report['checks'])} ncurses and locale probe groups | build {manifest['build_id']}")


if __name__ == '__main__':
    main()
