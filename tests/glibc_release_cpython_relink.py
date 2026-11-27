# SPDX-License-Identifier: Apache-2.0
"""Run the released and relinked CPython with the exact packaged standard library."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cpython_py0b_smoke import run
from make_work_disk import create_fat32
from package_cpython_glibc import LANDMARK, LIBRARY, PACKAGE, PROGRAM
from package_p2_faults import boot_maintenance_guest, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file, verify_package
from xypm_image import Disk

ELF_PATH = '/' + PROGRAM
COMMAND = 'exec-file ' + ELF_PATH
MARKER = '[CPYTHON_RELINK_EXIT]'
CASES = (
    ('version', COMMAND + ' --version', 0, 'Python 3.14.9'),
    ('compression', COMMAND + ' -B /tests/zlib.py', 0,
     'PY3_A2_OK zlib streaming gzip deflate_zip zipimport truncated corrupted crc'),
    ('absent_file', COMMAND + ' -B /tests/absent.py', 2, "can't open file"),
)
PRODUCTS = ('/work/py3a2/payload.gz', '/work/py3a2/payload.zip')


def library_inputs(package, digest, profile, work):
    wanted = {LIBRARY: work / 'python314.zip', LANDMARK: work / 'os.py'}

    def capture(event, item, data):
        path = wanted.get(item['path'])
        if path is None:
            return
        if event == 'begin':
            path.touch(exist_ok=False)
        elif event == 'data':
            with path.open('ab') as stream:
                stream.write(data)

    manifest = verify_package(package, profile, expected_sha256=digest, sink=capture)['manifest']
    binary, = (item for item in manifest['files'] if item['role'] == 'executable')
    require(manifest['id'] == PACKAGE and binary['path'] == PROGRAM
            and set(wanted) <= {item['path'] for item in manifest['files']}, 'wrong release Python or library')
    return binary['sha256'], wanted


def check_phase(iso, build_id, disk, output, substituted):
    phase = 'replacement' if substituted else 'original'
    guest = boot_maintenance_guest(iso, 'release_cpython_relink_' + phase, disk)
    try:
        require(('build=' + build_id).encode() in guest.output, 'wrong released system')
        baseline = resources(guest)
        observed = {}
        for name, command, status, wanted in CASES:
            text = run(guest, command, timeout=180)
            markers = text.splitlines().count(MARKER)
            require(wanted in text and f'kind=exited code={status}\n' in text and markers == int(substituted),
                    'wrong Python observation: ' + phase + ' ' + name)
            require(resources(guest) == baseline, 'resource drift: ' + phase + ' ' + name)
            observed[name] = {'exit': status, 'exit_markers': markers, 'output': wanted}
        start = len(guest.output)
        send_bytes(guest, b'sync\r')
        guest.expect(b'[files] sync=ok', start=start, timeout=30)
        guest.expect_supervisor(start=start, timeout=30)
        return {'resources': list(baseline), 'cases': observed}
    finally:
        guest.close()
        (output / (phase + '.serial')).write_bytes(guest.output)


def check(args):
    release_path = args.release / 'release_manifest.json'
    require(sha_file(release_path) == args.release_sha256, 'release manifest differs')
    release = load_json(release_path)
    iso = args.release / 'images/xos-install.iso'
    profile = args.release / 'application-sdk/profile.json'
    require(sha_file(iso) == release['system']['iso']['sha256']
            and sha_file(profile) == release['application_sdk']['profile_file_sha256'], 'release ISO or profile differs')
    original = sha_file(args.original)
    replacement = sha_file(args.replacement)
    require(replacement == args.replacement_sha256 != original, 'replacement Python differs')
    build_id = release['system']['build_id']
    package = args.release / 'packages/cpython.xpk'
    package_digest = release['packages']['cpython']['sha256']
    args.output.mkdir(parents=True)
    with TemporaryDirectory(dir=args.output) as folder:
        work = Path(folder)
        binary, library = library_inputs(package, package_digest, load_json(profile), work)
        require(original == binary, 'original interpreter differs from the frozen XPK')
        disk = work / 'relink.img'
        create_fat32(disk, 512)
        probe = ROOT / 'tests/fixtures/cpython_py3_a2/zlib_probe.py'
        with Disk(disk, work) as fat:
            for name in ('/usr', '/usr/bin', '/usr/lib', '/usr/lib/python3.14', '/tests', '/work', '/work/py3a2'):
                fat.command('mkdir', name)
            fat.command('import', ELF_PATH, args.original)
            for name, source in library.items():
                fat.command('import', '/' + name, source)
            fat.command('import', '/tests/zlib.py', probe)
        first = check_phase(iso, build_id, disk, args.output, False)
        with Disk(disk, work) as fat:
            require(sha_file(fat.export(ELF_PATH)) == original, 'original interpreter changed')
            products = {name: sha_file(fat.export(name)) for name in PRODUCTS}
            for name in PRODUCTS:
                fat.command('remove', name)
            fat.command('remove', ELF_PATH)
            fat.command('import', ELF_PATH, args.replacement)
        second = check_phase(iso, build_id, disk, args.output, True)
        with Disk(disk, work, True) as fat:
            require(sha_file(fat.export(ELF_PATH)) == replacement
                    and all(disk_sha == sha_file(fat.export(name)) for name, disk_sha in products.items())
                    and all(sha_file(fat.export('/' + name)) == sha_file(file) for name, file in library.items()),
                    'relinked interpreter output or packaged library changed')
        library_digests = {name: sha_file(file) for name, file in library.items()}
    results = {'status': 'passed_subset', 'build_id': build_id, 'release_manifest_sha256': args.release_sha256,
               'ordinary_iso_sha256': sha_file(iso), 'cpython_xpk_sha256': package_digest,
               'original_sha256': original, 'replacement_sha256': replacement, 'library_sha256': library_digests,
               'output_sha256': products, 'original': first, 'replacement': second, 'probe_sha256': sha_file(probe),
               'qemu': subprocess.check_output([os.environ.get('QEMU', 'qemu-system-x86_64'), '--version'],
                                               text=True).splitlines()[0],
               'serial_sha256': {phase: sha_file(args.output / (phase + '.serial'))
                                 for phase in ('original', 'replacement')},
               'runner_sha256': sha_file(Path(__file__))}
    (args.output / 'report.json').write_bytes(canonical(results))
    print('PASS released CPython and replacement with the exact packaged standard library')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'original', 'replacement', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('release-sha256', 'replacement-sha256'):
        parser.add_argument('--' + name, required=True)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
