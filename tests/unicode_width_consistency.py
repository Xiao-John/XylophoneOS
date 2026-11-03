# SPDX-License-Identifier: Apache-2.0
"""Compare the freestanding width helper against the locked newlib source tables."""
import argparse
import hashlib
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = '6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3'
TABLE_SHA = {'combining': '7b5b2544a32a522950c6c23ac64548c1b85dccb2765a9323cdc398a3e919590f',
             'wide': '326a00aefd15e5d914424ccf54c400f79f1e4c42810565ac93a0c878b1efe402'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='locked newlib source archive')
    args = parser.parse_args()
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != ARCHIVE_SHA:
        raise SystemExit('newlib source archive hash mismatch')
    expected = bytearray([1]) * 0x110000
    with tarfile.open(args.archive) as archive:
        for name in ('wide', 'combining'):
            member = 'newlib-4.6.0.20260123/newlib/libc/string/' + name + '.t'
            data = archive.extractfile(member).read()
            if hashlib.sha256(data).hexdigest() != TABLE_SHA[name]:
                raise SystemExit(name + ' table hash mismatch')
            previous = -1
            for start, end in re.findall(rb'\{\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+)\s*\}', data):
                first, last = int(start, 16), int(end, 16)
                if first <= previous or last < first or last >= len(expected):
                    raise SystemExit(name + ' table is not sorted')
                expected[first:last + 1] = bytes([0 if name == 'combining' else 2]) * (last - first + 1)
                previous = last
    expected[0] = 0
    source = '''#include <cstdio>\n#include <xos/text.hpp>\nint main() { for (unsigned c = 0; c <= 0x10ffff; ++c)\n  std::putchar(xos::text::width(c)); }\n'''
    with tempfile.TemporaryDirectory(prefix='xos-width-') as folder:
        cpp, exe = Path(folder) / 'probe.cpp', Path(folder) / 'probe'
        cpp.write_text(source)
        subprocess.run(['c++', '-std=c++17', '-O2', '-I', str(ROOT / 'src/user/include'),
                        '-I', str(ROOT / 'src/shared/include'), str(cpp), '-o', str(exe)], check=True)
        actual = subprocess.check_output([str(exe)])
    for cp in list(range(0, 1)) + list(range(0x20, 0x7f)) + list(range(0xa0, 0xd800)) + list(range(0xe000, 0x110000)):
        if actual[cp] != expected[cp]:
            raise SystemExit(f'width mismatch at U+{cp:04X}: {actual[cp]} != {expected[cp]}')
    print('PASS: valid printable scalar width profile matches locked newlib tables (host)')


if __name__ == '__main__':
    main()
