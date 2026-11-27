# SPDX-License-Identifier: Apache-2.0
"""Run original and relinked release GNU Make with Xshell and Dash in ordinary guests."""

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
from package_p2_faults import boot_maintenance_guest, resources
from task_smoke import send_bytes
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import Disk

GMAKE = '/usr/bin/gmake'
DASH = '/usr/bin/dash'
MARKER = '[GMAKE_RELINK_EXIT]'
MAKE = 'gmake -B -r -f /work/Makefile'
MAKEFILE = r"""SHELL := /usr/bin/dash
include /work/vars.mk
.PHONY: all fail
all: /out/gmake-stamp
	@printf 'GMAKE_RELINK_RECIPE=%s\n' '$(WORD)';
/out/gmake-stamp:
	@printf 'linked %s\n' '$(WORD)' > $@
fail:
	@exit 7;
"""
CASES = (
    ('version', 'gmake --version', 0, ('GNU Make 4.4.1',)),
    ('xshell_recipe', MAKE + ' WORD=xshell all', 0, ('GMAKE_RELINK_RECIPE=xshell',)),
    ('xshell_recipe_failure', MAKE + ' fail', 2, ('Error 7',)),
    ('dash_recipe', 'dash /work/run.sh', 0, ('GMAKE_RELINK_RECIPE=dash', 'GMAKE_RELINK_DASH_OK')),
)


def check_guest(iso, build_id, disk, output, substituted):
    phase = 'replacement' if substituted else 'original'
    guest = boot_maintenance_guest(iso, 'release_make_relink_' + phase, disk)
    try:
        require(('build=' + build_id).encode() in guest.output, 'wrong system build')
        baseline = resources(guest)
        observed = {}
        for name, command, status, expected in CASES:
            text = run(guest, command, timeout=75)
            markers = text.splitlines().count(MARKER)
            require(all(part in text for part in expected) and f'kind=exited code={status}\n' in text
                    and markers == int(substituted), 'wrong GNU Make observation: ' + phase + ' ' + name)
            require(resources(guest) == baseline, 'resource drift: ' + phase + ' ' + name)
            observed[name] = {'exit': status, 'exit_markers': markers, 'output': list(expected)}
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
    base = args.release / 'images'
    seed_path = base / 'gnu_seed_receipt.json'
    require(sha_file(seed_path) == release['gnu_seed']['receipt']['sha256'], 'GNU Seed receipt differs')
    seed = load_json(seed_path)
    iso = base / 'xos-install.iso'
    build_id = release['system']['build_id']
    require(sha_file(iso) == release['system']['iso']['sha256'], 'release ISO differs')
    original = sha_file(args.original)
    replacement = sha_file(args.replacement)
    require(original == seed['installed_files'][GMAKE]
            and replacement == args.replacement_sha256 != original
            and sha_file(args.dash) == release['dash_sha256'], 'guest executable inputs differ')

    args.output.mkdir(parents=True)
    with TemporaryDirectory(dir=args.output) as folder:
        work = Path(folder)
        disk = work / 'install.img'
        create_fat32(disk, 512)
        probe = work / 'Makefile'
        probe.write_text(MAKEFILE)
        vars_file = work / 'vars.mk'
        vars_file.write_text('WORD = default\n')
        script = work / 'run.sh'
        script.write_text('set -e\n' + MAKE + " WORD=dash all\nprintf 'GMAKE_RELINK_DASH_OK\\n'\n")
        with Disk(disk, work) as fat:
            for name in ('/usr', '/usr/bin', '/work', '/out'):
                fat.command('mkdir', name)
            for dest, source in ((GMAKE, args.original), (DASH, args.dash), ('/work/Makefile', probe),
                                 ('/work/vars.mk', vars_file), ('/work/run.sh', script)):
                fat.command('import', dest, source)
        original_result = check_guest(iso, build_id, disk, args.output, False)
        with Disk(disk, work) as fat:
            require(sha_file(fat.export(GMAKE)) == original
                    and fat.export('/out/gmake-stamp').read_bytes() == b'linked dash\n', 'original fixture contents differ')
            fat.command('remove', '/out/gmake-stamp')
            fat.command('remove', GMAKE)
            fat.command('import', GMAKE, args.replacement)
        replacement_result = check_guest(iso, build_id, disk, args.output, True)
        with Disk(disk, work, True) as fat:
            require(sha_file(fat.export(GMAKE)) == replacement and sha_file(fat.export(DASH)) == release['dash_sha256']
                    and fat.export('/out/gmake-stamp').read_bytes() == b'linked dash\n', 'replacement fixture contents differ')

    result = {'status': 'passed_subset', 'build_id': build_id, 'release_manifest_sha256': args.release_sha256,
              'ordinary_iso_sha256': sha_file(iso), 'gnu_seed_receipt_sha256': sha_file(seed_path),
              'original_sha256': original, 'replacement_sha256': replacement, 'dash_sha256': release['dash_sha256'],
              'original': original_result, 'replacement': replacement_result,
              'qemu': subprocess.check_output([os.environ.get('QEMU', 'qemu-system-x86_64'), '--version'],
                                              text=True).splitlines()[0],
              'serial_sha256': {phase: sha_file(args.output / (phase + '.serial'))
                                for phase in ('original', 'replacement')},
              'runner_sha256': sha_file(Path(__file__))}
    (args.output / 'report.json').write_bytes(canonical(result))
    print('PASS released GNU Make and replacement in Xshell and Dash')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('release', 'original', 'replacement', 'dash', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    for name in ('release-sha256', 'replacement-sha256'):
        parser.add_argument('--' + name, required=True)
    check(parser.parse_args())


if __name__ == '__main__':
    main()
