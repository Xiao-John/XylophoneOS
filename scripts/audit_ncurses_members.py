# SPDX-License-Identifier: Apache-2.0
"""Inventory one ncurses target archive against its pinned source and compile log.

This is provenance and notice screening, not a legal opinion or a transitive
header/source license audit. Generated-source dependencies are declared below.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'src/ports/ncurses/source_lock.json'
GENERATORS = {
    'lib_gen': ['ncurses/base/MKlib_gen.sh', 'include/curses.h.in'],
    'expanded': ['ncurses/tty/MKexpanded.sh', 'ncurses/curses.priv.h'],
    'codes': ['ncurses/tinfo/MKcodes.awk', 'include/Caps', 'include/Caps-ncurses'],
    'names': ['ncurses/tinfo/MKnames.awk', 'include/Caps', 'include/Caps-ncurses'],
    'fallback': ['ncurses/tinfo/MKfallback.sh', 'misc/terminfo.src'],
    'unctrl': ['ncurses/base/MKunctrl.awk'],
    'comp_userdefs': ['ncurses/tinfo/MKuserdefs.sh', 'include/Caps', 'include/Caps-ncurses'],
    'lib_keyname': ['ncurses/base/MKkeyname.awk', 'ncurses/tinfo/MKkeys_list.sh', 'include/Caps', 'include/Caps-ncurses'],
    'comp_captab': ['ncurses/tinfo/MKcaptab.sh', 'ncurses/tinfo/MKcaptab.awk', 'include/Caps', 'include/Caps-ncurses'],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source_archive, probe = args.archive.resolve(strict=True), args.probe.resolve(strict=True)
    lock = json.loads(LOCK.read_text())
    if sha(source_archive.read_bytes()) != lock['archive_sha256']:
        raise SystemExit('source archive hash mismatch')
    report = json.loads((probe / 'report.json').read_text())
    library = probe / 'build/lib/libncursesw.a'
    if sha(library.read_bytes()) != report['archive_sha256'] or report['source_sha256'] != lock['archive_sha256']:
        raise SystemExit('archive or source differs from ncurses probe receipt')
    names = subprocess.check_output(['x86_64-elf-ar', 't', str(library)], text=True).splitlines()
    if len(names) != len(set(names)) or len(names) != report['archive_member_count']:
        raise SystemExit('duplicate members or member count mismatch')
    commands = {}
    for line in (probe / 'make.log').read_text().splitlines():
        match = re.search(r'\s-c\s+(\S+\.c)\s+-o\s+\S*/([^/\s]+\.o)(?:\s|$)', line)
        if match:
            source, obj = match.groups()
            if obj in commands:
                raise SystemExit('multiple compilation commands for ' + obj)
            commands[obj] = source
    if not set(names).issubset(commands):
        raise SystemExit('archive member missing from compile log')
    rows = []
    with tarfile.open(source_archive) as tar:
        def upstream(relative):
            member = tar.getmember('ncurses-6.5/' + relative)
            data = tar.extractfile(member).read()
            return {'path': relative, 'sha256': sha(data),
                    'permission_notice_present': b'Permission is hereby granted' in data}
        source_root = probe / 'ncurses-6.5'
        for name in names:
            source = Path(commands[name])
            if not source.is_absolute():
                source = (probe / 'build/ncurses' / source).resolve(strict=True)
            data = source.read_bytes()
            object_bytes = subprocess.check_output(['x86_64-elf-ar', 'p', str(library), name])
            if sha(object_bytes) != sha((probe / 'build/objects' / name).read_bytes()):
                raise SystemExit('archive member differs from compiled object: ' + name)
            row = {'member': name, 'object_sha256': sha(object_bytes), 'compiled_source_sha256': sha(data)}
            if source.is_relative_to(source_root):
                entry = upstream(source.relative_to(source_root).as_posix())
                if sha(data) != entry['sha256']:
                    raise SystemExit('source differs from archive: ' + str(source))
                row.update(kind='upstream_source', inputs=[entry])
            else:
                stem = name.removesuffix('.o')
                if stem not in GENERATORS or source != (probe / 'build/ncurses' / (stem + '.c')).resolve():
                    raise SystemExit('unrecognized generated source: ' + str(source))
                row.update(kind='generated_source', inputs=[upstream(p) for p in GENERATORS[stem]])
            rows.append(row)
    result = {'status': 'provenance_screened_not_legal_review', 'source_archive_sha256': lock['archive_sha256'],
              'target_archive_sha256': report['archive_sha256'], 'compile_log_sha256': sha((probe / 'make.log').read_bytes()),
              'member_count': len(rows), 'members': rows,
              'limitations': ['generated dependency list is non-transitive', 'headers and terminfo data are not fully reviewed',
                              'notice substring is not a license classification', 'newlib is not reviewed']}
    if args.output.exists():
        raise SystemExit('output already exists')
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'members': len(rows),
                      'generated': sum(r['kind'] == 'generated_source' for r in rows)}))


if __name__ == '__main__':
    main()
