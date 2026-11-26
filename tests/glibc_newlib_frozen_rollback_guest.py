# SPDX-License-Identifier: Apache-2.0
"""Replay a selected glibc SDK and rollback to the original 1024 release."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from build_candidate import inspect_app_kit
from make_work_disk import create_fat32
from package_p2_faults import sparse_copy
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json, require, sha_file, strict_json, verify_package

FROZEN_RELEASE = ROOT / 'docs/releases/release_0_0_1_1024.json'
FROZEN_PROFILE = ROOT / 'config/package/xos_x86_64_static_single_v1.json'
HISTORICAL = ROOT / 'docs/reports/glibc_release_1024_rollback_20261126/historical_rollback.json'
SEED = b'frozen-user-data\n'


def xypm(profile, *arguments, rejection=None):
    command = [sys.executable, str(ROOT / 'scripts/xypm.py'), *map(str, arguments),
               '--profile', str(profile)]
    result = subprocess.run(command, capture_output=True, text=True)
    if rejection is None:
        require(result.returncode == 0, result.stderr)
    else:
        require(result.returncode != 0 and rejection in result.stderr, result.stderr)
    return result.stdout if rejection is None else result.stderr


def install(profile, package, disk, output, rejection=None):
    return xypm(profile, 'install', package, '--offline', '--image', disk,
                '--output-image', output, rejection=rejection)


def seed_disk(disk, seed, content):
    seed.write_bytes(content)
    transfer(disk, 'mkdir', '/state')
    transfer(disk, 'import', '/state/user.txt', seed)


def readback(disk, guest_path, file):
    file.unlink(missing_ok=True)
    transfer(disk, 'export', guest_path, file)
    return file.read_bytes()


def executable(package, profile, path, *, binding=None):
    build_receipt = bytearray()
    verified = verify_package(package, load_json(profile))
    manifest = verified['manifest']
    receipt_path = manifest['build_receipt']['path']

    def capture(event, item, chunk):
        if event == 'data' and item['path'] == receipt_path:
            build_receipt.extend(chunk)

    verify_package(package, load_json(profile), expected_sha256=verified['sha256'], sink=capture)
    receipt = strict_json(bytes(build_receipt))
    if binding is not None:
        require(receipt['runtime_family'] == 'glibc' and
                all(receipt[key] == binding[key] for key in
                    ('sdk_manifest_sha256', 'sdk_tree_sha256', 'profile_sha256')),
                'glibc application receipt does not bind the selected SDK')
    descriptor = next(item for item in manifest['files'] if item['path'] == path.removeprefix('/'))
    return {'id': manifest['id'], 'package_sha256': verified['sha256'], 'elf_sha256': descriptor['sha256'],
            'build_receipt_sha256': hashlib.sha256(build_receipt).hexdigest(),
            'sdk_tree_sha256': receipt['sdk_tree_sha256'],
            'compiler_sha256': receipt['compiler']['sha256'],
            'project_inputs': receipt['inputs']}


def repack_with_kit(kit, project, output):
    destination = output.with_suffix('')
    shutil.copytree(project, destination, ignore=shutil.ignore_patterns('build'))
    command = [sys.executable, str(kit / 'xos-app')]
    subprocess.run([*command, 'build', destination], check=True)
    subprocess.run([*command, 'check', destination], check=True)
    subprocess.run([*command, 'pack', destination, '--output', output], check=True)


def guest_command(guest, value, prompt, marker, timeout=45):
    offset = len(guest.output)
    send_bytes(guest, value.encode() + b'\r')
    guest.expect(marker, start=offset, timeout=timeout)
    guest.expect(prompt, start=guest.output.index(marker, offset), timeout=45)
    return bytes(guest.output[offset:])


def guest_run(output, image, disk, name, build_id, commands, *, historical=False):
    cpu = 'qemu64' if historical else 'qemu64,+rdrand'
    guest = Guest(image, name, cpu=cpu, iso=not historical, work_disk=disk,
                  log_dir=output, qmp_enabled=False)
    prompt = b'sup> ' if historical else b'xsh> '
    try:
        guest.expect(b'xos64> ', timeout=60)
        require(b'build=' + build_id.encode() in guest.output, 'guest reported a different build ID')
        start = len(guest.output)
        send_bytes(guest, b'run\r')
        guest.expect(prompt, start=start, timeout=60)
        if not historical:
            guest.expect_supervisor(trace=True, start=start, timeout=30)
        guest_command(guest, 'demo quiet', prompt, b'[sup] demo tasks')

        def resources():
            text = guest_command(guest, 'stats', prompt, b'[resources] free=')
            match = re.search(rb'free=(\d+) tasks=(\d+) completions=(\d+)', text)
            if match is None:
                raise AssertionError('guest did not report resource counts')
            return tuple(map(int, match.groups()))

        baseline = resources()
        for invocation, marker in commands:
            result = guest_command(guest, invocation, prompt, b'kind=exited code=0', timeout=120)
            require(marker in result and resources() == baseline,
                    'application output or post-exit resource counts differ')
        guest_command(guest, 'sync', prompt, b'[files] sync=ok')
        return {'build_id': build_id, 'resources_before_and_after': baseline,
                'app_markers': [marker.decode() for _, marker in commands]}
    finally:
        guest.close()


def verify_release_file(info, path, archive_suffix):
    record = next(asset for asset in info['assets'] if asset['name'].endswith(archive_suffix))
    digest = sha_file(path)
    require(path.stat().st_size == record['size'] and 'sha256:' + digest == record['digest'],
            'input differs from the frozen release asset')
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('frozen-images', 'frozen-sdk', 'frozen-boot', 'frozen-disk', 'frozen-xpk',
                  'repack-before', 'legacy-project', 'unpacked-sdk', 'kit', 'candidate',
                  'c-xpk', 'cpp-xpk', 'c-project', 'cpp-project', 'output'):
        parser.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'replay_source_commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'runner_sha256': sha_file(Path(__file__)),
        'qemu_version': subprocess.check_output(['qemu-system-x86_64', '--version'],
                                                text=True).splitlines()[0], 'guests': {}}
    try:
        release = load_json(FROZEN_RELEASE)
        previous = load_json(HISTORICAL)['input_sha256']
        sdk_digest = verify_release_file(release, args.frozen_sdk, '_sdk.tar.gz')
        archive_digest = verify_release_file(release, args.frozen_images, '_images.tar.gz')
        boot_digest = verify_release_file(release, args.frozen_boot, '_boot.img')
        disk_digest = sha_file(args.frozen_disk)
        old = executable(args.frozen_xpk, FROZEN_PROFILE, '/usr/bin/frozen')
        require(disk_digest == previous['published_work_disk'] and
                sha_file(FROZEN_PROFILE) == previous['frozen_profile'] and
                old['package_sha256'] == previous['frozen_probe_package'] == sha_file(args.repack_before),
                'input disk, profile, or reproduced app differs from historical evidence')
        report['frozen'] = {'release_commit': release['source_commit'], 'boot_sha256': boot_digest,
                            'images_archive_sha256': archive_digest, 'published_disk_sha256': disk_digest,
                            'sdk_archive_sha256': sdk_digest, 'profile_sha256': sha_file(FROZEN_PROFILE),
                            'application': old}
        candidate_file = args.candidate / 'candidate_manifest.json'
        candidate = load_json(candidate_file)
        new_profile = args.kit / 'profile.json'
        binding = inspect_app_kit(args.kit)
        require(candidate['installer_guest_qualification'] == 'passed' and
                candidate['application_sdk'] == binding, 'candidate kit binding differs')
        image = args.candidate / 'system/xos-install.iso'
        image_hash = sha_file(image)
        require(image_hash == candidate['artifacts']['system/xos-install.iso'], 'ordinary ISO differs')
        report['glibc'] = {'candidate_manifest_sha256': sha_file(candidate_file),
                           'candidate_source_commit': candidate['source_commit'],
                           'ordinary_iso_sha256': image_hash, 'sdk_binding': binding}
        output = args.output
        old_seed = output / 'old-seed.img'
        old_disk = output / 'old-work.img'
        new_blank = output / 'new-blank.img'
        new_c = output / 'new-c.img'
        new_disk = output / 'new-work.img'
        scratch = output / 'scratch.bin'
        # The installer locks its input writable even when it creates a separate output.
        sparse_copy(args.frozen_disk, old_seed)
        require(sha_file(old_seed) == disk_digest, 'copy differs from the released work disk')
        install(FROZEN_PROFILE, args.frozen_xpk, old_seed, old_disk)
        require(sha_file(old_seed) == disk_digest, 'install changed its input disk')
        old_seed.unlink()
        seed_disk(old_disk, scratch, SEED)
        report['guests']['before'] = guest_run(output, args.frozen_boot, old_disk, 'before',
            release['system_build_id'], [('exec-file /usr/bin/frozen before', b'FROZEN_RUNTIME_OK before')],
            historical=True)
        require(readback(old_disk, '/state/user.txt', scratch) == SEED + b'before\n', 'first append missing')
        require(hashlib.sha256(readback(old_disk, '/usr/bin/frozen', scratch)).hexdigest() == old['elf_sha256'],
                'old installed ELF differs before selection')
        old_before = sha_file(old_disk)
        replay_c = output / 'replayed-c.xpk'
        replay_cpp = output / 'replayed-cpp.xpk'
        applications = []
        for project, reference, package, path in (
                (args.c_project, args.c_xpk, replay_c, '/usr/bin/kit_c'),
                (args.cpp_project, args.cpp_xpk, replay_cpp, '/usr/bin/kit_cpp')):
            repack_with_kit(args.kit, project, package)
            expected = executable(reference, new_profile, path, binding=binding)
            actual = executable(package, new_profile, path, binding=binding)
            require(actual['id'] == expected['id'] and actual['project_inputs'] == expected['project_inputs'],
                    'selected kit build used different project inputs')
            actual['reference_package_sha256'] = expected['package_sha256']
            applications.append(actual)
        report['glibc']['applications'] = applications
        xypm(FROZEN_PROFILE, 'verify', replay_c, rejection='package target profile mismatch')
        refused = output / 'forbidden-mixed.img'
        install(new_profile, replay_c, old_disk, refused, rejection='database profile mismatch')
        require(not refused.exists() and sha_file(old_disk) == old_before, 'rejected install changed old disk')

        create_fat32(new_blank, 512)
        install(new_profile, replay_c, new_blank, new_c)
        install(new_profile, replay_cpp, new_c, new_disk)
        seed_disk(new_disk, scratch, b'glibc-user-data\n')
        report['guests']['glibc'] = guest_run(output, image, new_disk, 'glibc', candidate['build_id'],
            [('exec-file /usr/bin/kit_c', b'GLIBC_KIT_C_OK 2.44'),
             ('exec-file /usr/bin/kit_cpp', b'GLIBC_KIT_CPP_OK vector thread exception')])
        xypm(new_profile, 'verify-installed', '--image', new_disk)
        require(readback(new_disk, '/state/user.txt', scratch) == b'glibc-user-data\n', 'new guest data differs')
        for path, application in zip(('/usr/bin/kit_c', '/usr/bin/kit_cpp'), applications, strict=True):
            require(hashlib.sha256(readback(new_disk, path, scratch)).hexdigest() == application['elf_sha256'],
                    'installed glibc ELF differs from the SDK build receipt')
        report['glibc']['work_disk_sha256'] = sha_file(new_disk)
        require(sha_file(image) == image_hash, 'ordinary ISO changed during replay')
        xypm(new_profile, 'verify', args.frozen_xpk, rejection='package target profile mismatch')
        require(sha_file(old_disk) == old_before, 'selecting glibc changed the old work disk')
        report['frozen']['disk_before_and_after_glibc_sha256'] = old_before
        report['cross_profile_refusals'] = ['new XPK under old profile', 'new XPK onto old database',
                                           'old XPK under new profile']

        old_tool = [sys.executable, str(ROOT / 'scripts/xos_app.py'), '--profile', str(FROZEN_PROFILE)]
        subprocess.run([*old_tool, 'build', args.legacy_project, '--sdk', args.unpacked_sdk], check=True)
        subprocess.run([*old_tool, 'check', args.legacy_project, '--sdk', args.unpacked_sdk], check=True)
        after = output / 'frozen-after.xpk'
        subprocess.run([*old_tool, 'pack', args.legacy_project, '--sdk', args.unpacked_sdk,
                        '--output', after], check=True)
        require(sha_file(after) == old['package_sha256'], 'frozen project did not reproduce after selection')
        xypm(FROZEN_PROFILE, 'verify-installed', '--image', old_disk)
        report['guests']['after'] = guest_run(output, args.frozen_boot, old_disk, 'after',
            release['system_build_id'], [('exec-file /usr/bin/frozen after', b'FROZEN_RUNTIME_OK after')],
            historical=True)
        xypm(FROZEN_PROFILE, 'verify-installed', '--image', old_disk)
        require(hashlib.sha256(readback(old_disk, '/usr/bin/frozen', scratch)).hexdigest() == old['elf_sha256'],
                'old installed ELF differs after rollback')
        data = readback(old_disk, '/state/user.txt', scratch)
        require(data == SEED + b'before\nafter\n', 'rollback did not preserve the original and appended data')
        require(sha_file(args.frozen_disk) == disk_digest and sha_file(args.frozen_boot) == boot_digest,
                'a published input changed')
        (output / 'preserved_user_data.txt').write_bytes(data)
        report['frozen']['disk_after_rollback_sha256'] = sha_file(old_disk)
        report['status'] = 'passed_subset'
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(report['status'])


if __name__ == '__main__':
    main()
