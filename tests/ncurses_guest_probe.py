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
        apps.get('sdk_tree_sha256') != sdk_receipt.get('sdk_tree_sha256') or
        apps.get('probe_report_sha256') != sha(probe / 'report.json') or
        term.get('status') != 'built_guest_not_run' or
        target.get('source_sha256') != source_lock['archive_sha256'] or
        term.get('source_sha256') != source_lock['archive_sha256'] or
        term.get('source_lock_sha256') != sha(lock_path) or
        term.get('target_report_sha256') != sha(probe / 'report.json') or
        term.get('target_config_sha256') != sha(probe / 'build/include/ncurses_cfg.h') or
        term.get('target_library_sha256') != target.get('archive_sha256') or
        apps.get('ncurses_archive_sha256') != target.get('archive_sha256') or
        sha(probe / 'build/lib/libncursesw.a') != target.get('archive_sha256')):
        raise SystemExit('SDK, ncurses, consumer and terminfo receipts do not match')
    image, terminal = system / 'xos-install.iso', system / 'user_terminal.image.elf'
    for path in (image, terminal):
        if manifest['artifacts'].get(path.name, {}).get('sha256') != sha(path):
            raise SystemExit(f'system artifact differs from manifest: {path.name}')
    wide, reentry, locale, failure = (consumers / name for name in
        ('wide_screen_probe.elf', 'reentry_probe.elf', 'wide_locale_probe.elf', 'terminal_failure_probe.elf'))
    for path in (wide, reentry, locale, failure):
        if apps['artifacts'].get(path.name) != sha(path):
            raise SystemExit(f'consumer differs from receipt: {path.name}')
    entry = terminfo / 'terminfo' / term['entry']
    if term['entry'] != 'x/xterm' or not entry.is_file() or entry.is_symlink() or sha(entry) != term['entry_sha256']:
        raise SystemExit('terminfo data differs from receipt')
    report = {'status': 'failed', 'scope': 'bounded ncurses and locale probes, not full W1/W2 acceptance',
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'build_id': manifest['build_id'], 'system_sha256': sha(image), 'terminal_sha256': sha(terminal),
              'sdk_tree_sha256': sdk_receipt['sdk_tree_sha256'], 'ncurses_sha256': target['archive_sha256'],
              'terminfo_sha256': sha(entry), 'wide_sha256': sha(wide), 'reentry_sha256': sha(reentry),
              'locale_sha256': sha(locale), 'failure_sha256': sha(failure), 'checks': []}
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
                                        ('/bin/failure.elf', failure),
                                        ('/usr/local/share/terminfo/x/xterm', entry)):
                transfer(disk, 'import', destination, source)
            guest = Guest(image, 'ncurses_guest_probe', work_disk=disk, iso=True)
            guest.expect(b'xos64> ', timeout=30)
            send_bytes(guest, b'run\r')
            if args.xsh:
                guest.expect(b'xsh> ', timeout=45)
                start = len(guest.output)
                send_bytes(guest, b'tty-run /bin/wide.elf\r')
                guest.expect(b'W2_INPUT_READY', start=start, timeout=60)
                screen = bytes(guest.output[start:])
                if b'\xe4\xb8\xad\xcc\x81' not in screen or not re.search(rb'\x1b\[[0-9;]*31(?:;[0-9]*)?m', screen):
                    raise AssertionError('xsh wide screen output missing')
                send_bytes(guest, b'\x1bOD\xe4\xb8\xad\x1bOP')
                guest.expect(b'xsh> ', start=start, timeout=60)
                if any(s in bytes(guest.output[start:]) for s in (b'program exited with status', b'xsh: cannot')):
                    raise AssertionError('xsh wide consumer failed')
                report['checks'].append('xsh_terminal_wide_input_output')
                for program in ('reentry', 'locale'):
                    start = len(guest.output)
                    send_bytes(guest, ('tty-run /bin/' + program + '.elf\r').encode())
                    guest.expect(b'xsh> ', start=start, timeout=60)
                    if any(s in bytes(guest.output[start:]) for s in (b'program exited with status', b'xsh: cannot')):
                        raise AssertionError('xsh ' + program + ' consumer failed')
                    report['checks'].append('xsh_terminal_' + program)
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
            send_bytes(guest, b'\x1bOD\xe4\xb8\xad\x1bOP')
            marker = guest.expect_any((b'W2_WIDE_OK', b'W2_WIDE_FAILED'), timeout=60)
            if marker != b'W2_WIDE_OK':
                raise AssertionError('wide consumer returned failure')
            report['checks'].append('wide_window_color_combining_timeout_left_f1_cjk')
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
            report['checks'].append('application_read_error_on_terminal_death_and_recovery')
            report['status'] = 'passed_probe'
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            report['serial_sha256'] = hashlib.sha256(guest.output).hexdigest()
            guest.close()
        (system / 'ncurses_guest_probe_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"PASS {len(report['checks'])} ncurses and locale probe groups | build {manifest['build_id']}")


if __name__ == '__main__':
    main()
