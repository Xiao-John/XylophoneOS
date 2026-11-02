#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose an isolated ncursesw SDK candidate and its target xterm data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from xos_app import tree_receipt
from probe_ncursesw import PUBLIC_HEADERS

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk-candidate', 'ncurses-probe', 'terminfo', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    candidate, probe, terminfo = (p.resolve(strict=True) for p in
                                  (args.sdk_candidate, args.ncurses_probe, args.terminfo))
    output = args.output.resolve()
    check(not output.exists() and not any(output.is_relative_to(p) for p in
          (ROOT / 'src', ROOT / 'localpilot', candidate, probe, terminfo)),
          'output must be a new private directory')
    sdk = candidate / 'sdk'
    sdk_report = json.loads((candidate / 'receipt.json').read_text())
    target = json.loads((probe / 'report.json').read_text())
    term = json.loads((terminfo / 'receipt.json').read_text())
    lock_path = ROOT / 'src/ports/ncurses/source_lock.json'
    lock = json.loads(lock_path.read_text())
    notice = ROOT / 'src/ports/ncurses' / lock['notice']
    term_notice = ROOT / 'src/ports/ncurses/upstream/terminfo-source-notice.txt'
    term_source = terminfo / 'ncurses-6.5/misc/terminfo.src'
    notice_end = b'#------------------------------------------------------------------------------\n#\n#\tVersion 10.2.1'
    source_bytes = term_source.read_bytes()
    check(notice_end in source_bytes and term_notice.read_bytes() ==
          source_bytes.split(notice_end, 1)[0] + b'#------------------------------------------------------------------------------\n',
          'terminfo source notice differs from upstream header')
    library = probe / 'build/lib/libncursesw.a'
    entry = terminfo / 'terminfo/x/xterm'
    sdk_hash, _ = tree_receipt(sdk)
    check(sdk_report.get('status') == 'built_unverified' and sdk_hash == sdk_report.get('sdk_tree_sha256'),
          'SDK candidate does not match its receipt')
    for name, expected in sdk_report['inputs'].items():
        path = ROOT / name
        check(path.is_file() and sha(path) == expected, 'SDK source differs: ' + name)
    check(target.get('archive_valid') is True and target.get('inputs_unchanged') is True and
          target.get('sdk_tree_sha256') == sdk_hash and target.get('source_lock_sha256') == sha(lock_path) and
          target.get('source_sha256') == lock['archive_sha256'] and
          target.get('archive_sha256') == sha(library) and sha(notice) == lock['notice_sha256'] and
          '--disable-sigwinch' in target['configure_command'] and
          '-D_XOPEN_SOURCE=700' in target['environment']['CPPFLAGS'], 'ncurses inputs do not match')
    headers = target.get('public_headers_sha256', {})
    check(set(headers) == set(PUBLIC_HEADERS), 'target report lacks public header receipts')
    for name in PUBLIC_HEADERS:
        path = probe / 'build/include' / name
        check(path.is_file() and not path.is_symlink() and sha(path) == headers[name],
              'ncurses header differs: ' + name)
    check(term.get('status') == 'built_guest_not_run' and term.get('entry') == 'x/xterm' and
          term.get('source_sha256') == lock['archive_sha256'] and
          term.get('source_lock_sha256') == sha(lock_path) and
          term.get('target_report_sha256') == sha(probe / 'report.json') and
          term.get('target_config_sha256') == sha(probe / 'build/include/ncurses_cfg.h') and
          term.get('target_library_sha256') == sha(library) and not entry.is_symlink() and
          term.get('entry_sha256') == sha(entry) and term.get('terminfo_source_sha256') == sha(term_source) and
          term_source.read_bytes().startswith(term_notice.read_bytes()), 'terminfo inputs do not match')
    output.mkdir(parents=True)
    shutil.copytree(sdk, output / 'sdk')
    include = output / 'sdk/include/ncursesw'
    include.mkdir()
    for name in PUBLIC_HEADERS:
        shutil.copyfile(probe / 'build/include' / name, include / name)
    shutil.copyfile(library, output / 'sdk/lib/libncursesw.a')
    license_dir = output / 'sdk/licenses/ncurses'
    license_dir.mkdir()
    shutil.copyfile(notice, license_dir / 'COPYING')
    shutil.copyfile(term_notice, license_dir / 'terminfo-source-notice.txt')
    shutil.copyfile(lock_path, license_dir / 'source_lock.json')
    target_dir = output / 'target/usr/local/share/terminfo/x'
    target_dir.mkdir(parents=True)
    shutil.copyfile(entry, target_dir / 'xterm')
    check(tree_receipt(sdk)[0] == sdk_hash and sha(library) == target['archive_sha256'] and
          sha(entry) == term['entry_sha256'] and sha(term_source) == term['terminfo_source_sha256'] and
          term_source.read_bytes().startswith(term_notice.read_bytes()) and
          all(sha(probe / 'build/include' / n) == headers[n] for n in PUBLIC_HEADERS),
          'inputs changed during composition')
    digest, files = tree_receipt(output)
    receipt = {'status': 'built_unverified', 'scope': 'single-thread ncursesw SDK candidate and xterm data',
               'source_sha256': lock['archive_sha256'], 'base_sdk_tree_sha256': sdk_hash,
               'target_report_sha256': sha(probe / 'report.json'), 'terminfo_receipt_sha256': sha(terminfo / 'receipt.json'),
               'tree_sha256': digest, 'files': files}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'tree_sha256': digest, 'files': len(files)}, indent=2))


if __name__ == '__main__':
    main()
