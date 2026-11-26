# SPDX-License-Identifier: Apache-2.0
"""Relink a retained C object with a replacement libc and run both static ELFs."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from make_work_disk import create_fat32
from package_p2_faults import boot_maintenance_guest, resources
from task_smoke import send_bytes
from xypm_format import inspect_elf, load_json, require, sha_file
from xypm_image import Disk
from xypm_sdk_profile import verify_profile

SOURCE = ROOT / 'tests/fixtures/glibc_g4/libc_replacement.c'
TOOLS = ('x86_64-elf-gcc', 'x86_64-elf-as', 'x86_64-elf-ld')


def sdk_inputs(build, profile):
    binding = verify_profile(load_json(profile), 'glibc', build)
    manifest = load_json(build / 'manifest.json')
    libc = build / 'sysroot/usr/lib/libc.a'
    require(sha_file(libc) == manifest['artifacts']['usr/lib/libc.a'], 'libc digest differs')
    return binding, manifest, libc


def run_guest(image, disk, system, original, relinked, output):
    create_fat32(disk, 512)
    regular = output / 'regular.txt'
    regular.write_bytes(b'relink input\n')
    with Disk(disk, output) as host:
        host.command('mkdir', '/state')
        host.command('import', '/state/regular.txt', regular)
        host.command('import', '/base.elf', original)
        host.command('import', '/replacement.elf', relinked)
    guest = boot_maintenance_guest(image, 'glibc_static_libc_replacement', disk)
    try:
        require(b'build=' + system.encode() in guest.output, 'guest build ID differs')
        baseline = resources(guest)
        for elf, marker in (('/base.elf', b'STATIC_RELINK_BASE_STUBS'),
                            ('/replacement.elf', b'STATIC_RELINK_REPLACEMENT_PATH_API')):
            start = len(guest.output)
            send_bytes(guest, b'exec-file ' + elf.encode() + b'\r')
            guest.expect_supervisor(start=start, timeout=90)
            outcome = bytes(guest.output[start:])
            require(marker in outcome and b'kind=exited code=0' in outcome,
                    'unexpected guest result for ' + elf)
            require(resources(guest) == baseline, 'guest resources changed')
    finally:
        guest.close()
        (output / 'serial.log').write_bytes(guest.output)
    with Disk(disk, output, True) as host:
        for name, expected in (('/state/regular.txt', regular), ('/base.elf', original),
                               ('/replacement.elf', relinked)):
            require(sha_file(host.export(name)) == sha_file(expected), 'guest disk changed ' + name)
    return baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base-kit', 'replacement-sdk', 'replacement-profile', 'system', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    kit = arguments.base_kit.resolve(strict=True)
    replacement = arguments.replacement_sdk.resolve(strict=True)
    base_binding, base_manifest, base_libc = sdk_inputs(kit / 'sdk', kit / 'profile.json')
    new_binding, new_manifest, new_libc = sdk_inputs(replacement, arguments.replacement_profile)
    require(sha_file(base_libc) != sha_file(new_libc), 'replacement archive is identical')
    for name in TOOLS:
        require(base_manifest['tools'][name]['sha256'] == new_manifest['tools'][name]['sha256'],
                'SDK tools differ for ' + name)

    system_manifest = arguments.system / 'manifest.json'
    system = load_json(system_manifest)
    image = arguments.system / 'xos-install.iso'
    require(sha_file(image) == system['artifacts']['xos-install.iso']['sha256'], 'system ISO differs')
    original = output / 'base.elf'
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_glibc_program.py'),
                    '--sdk', str(kit / 'sdk/sysroot'), '--profile', str(kit / 'profile.json'),
                    '--source', str(SOURCE), '--output', str(original)], check=True)
    build = output / 'base.elf.build'
    receipt = load_json(build / 'manifest.json')
    require(receipt['elf_sha256'] == sha_file(original), 'builder ELF differs')
    retained = output / 'program_0.o'
    shutil.copyfile(build / retained.name, retained)
    object_digest = sha_file(retained)
    relinked = output / 'replacement.elf'
    command = next(step['command'] for step in receipt['steps'] if step['name'] == 'link')
    values = {str(base_libc): str(new_libc), str(build / retained.name): str(retained)}
    require(all(command.count(key) == 1 for key in values), 'expected single object and libc inputs')
    command = [values.get(argument, argument) for argument in command]
    command[command.index('-o') + 1] = str(relinked)
    with (output / 'replacement_link.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    require(sha_file(retained) == object_digest == sha_file(build / retained.name), 'compiled object changed')
    require(sha_file(original) != sha_file(relinked), 'replacement ELF is identical')
    for elf in (original, relinked):
        require(inspect_elf(elf)['static_tls'], 'ELF missing static TLS')

    report = {'status': 'failed', 'system_build_id': system['build_id'],
              'system_iso_sha256': sha_file(image), 'system_manifest_sha256': sha_file(system_manifest),
              'source_sha256': sha_file(SOURCE), 'runner_sha256': sha_file(Path(__file__)),
              'object_sha256': object_digest,
              'baseline': {**base_binding, 'sdk_manifest_sha256': sha_file(kit / 'sdk/manifest.json'),
                           'libc_sha256': sha_file(base_libc), 'elf_sha256': sha_file(original)},
              'replacement': {**new_binding, 'sdk_manifest_sha256': sha_file(replacement / 'manifest.json'),
                              'libc_sha256': sha_file(new_libc), 'elf_sha256': sha_file(relinked)},
              'qemu': subprocess.check_output(['qemu-system-x86_64', '--version'], text=True).splitlines()[0]}
    try:
        report['resources'] = run_guest(image, output / 'work.img', system['build_id'], original,
                                        relinked, output)
        require(sha_file(base_libc) == report['baseline']['libc_sha256'] and
                sha_file(new_libc) == report['replacement']['libc_sha256'], 'SDK changed')
        report['status'] = 'passed_subset'
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
