# SPDX-License-Identifier: Apache-2.0
"""Explicit OFFLINE file transfer to a regular XOS disk image. Never run with QEMU open."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def host_tool():
    sources = [ROOT / 'scripts/work_disk_host.cpp', ROOT / 'src/third_party/fatfs/ff.c',
               ROOT / 'src/user/services/fatfs_unicode.cpp']
    headers = list((ROOT / 'src/third_party/fatfs').glob('*.h'))
    digest = hashlib.sha256(b''.join(p.read_bytes() for p in sources + sorted(headers))).hexdigest()
    output = ROOT / 'build/work_disk_host'
    stamp = output.with_suffix('.sha256')
    if not output.exists() or not stamp.exists() or stamp.read_text() != digest:
        output.parent.mkdir(exist_ok=True)
        subprocess.run([shutil.which('clang++') or 'c++', '-std=c++17', '-O2', '-w',
                        '-I', str(ROOT / 'src/third_party/fatfs'), *map(str, sources),
                        '-o', str(output)], check=True)
        stamp.write_text(digest)
    return output

def transfer(image, operation, path, source=None):
    image = Path(image)
    if image.is_symlink() or not image.is_file():
        raise ValueError('Expected an existing regular image, not a symlink or device')
    if not path.startswith('/') or any(x in ('.', '..') for x in path.split('/')):
        raise ValueError('Use an absolute guest path without dot components')
    try:
        encoded = path.encode('utf-8', 'strict')
    except UnicodeError as error:
        raise ValueError('Expected a valid UTF-8 path') from error
    if len(encoded) >= 256 or any(ord(c) < 32 or ord(c) == 127 for c in path):
        raise ValueError('Invalid or overlong UTF-8 path')
    for component in path.split('/'):
        if component.upper().startswith('XOS') and component.upper().endswith('.TMP'):
            raise ValueError('Reserved recovery name')
    command = [str(host_tool()), str(image.resolve()), operation, path]
    if source is not None:
        command.append(str(Path(source).resolve()))
    subprocess.run(command, check=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('operation', choices=('mkdir','import','export'))
    parser.add_argument('path', help='absolute guest path; import never overwrites')
    parser.add_argument('source', nargs='?', help='host input/output for import/export')
    args=parser.parse_args()
    if (args.operation=='mkdir') != (args.source is None):
        parser.error('import/export require a host file; mkdir does not')
    transfer(args.image,args.operation,args.path,args.source)
if __name__=='__main__': main()
