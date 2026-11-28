#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a new rollback fixture with the verified original 1024 SDK and media."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from glibc_newlib_frozen_rollback_guest import executable, readback, seed_disk, verify_release_file
from package_application_preview import FROZEN_PROFILE, FROZEN_RELEASE
from package_p2_faults import sparse_copy
from xos_sdk import inspect as inspect_sdk
from xypm_format import canonical, load_json, require, sha_file

SEED = b'p0-r1-frozen-user-data\n'
SOURCE_NAMES = ('tests/prepare_frozen_rollback.py', 'tests/fixtures/sdk_rollback/frozen.c',
    'tests/glibc_newlib_frozen_rollback_guest.py', 'tests/package_p2_faults.py',
    'scripts/xos_sdk.py', 'scripts/xos_app.py', 'scripts/xypm.py', 'scripts/xypm_format.py',
    'scripts/xypm_image.py', 'scripts/work_disk.py', 'scripts/package_application_preview.py',
    'docs/releases/release_0_0_1_1024.json', 'config/package/xos_x86_64_static_single_v1.json', 'LICENSE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    frozen = args.frozen_directory.resolve(strict=True)
    out = args.output.resolve()
    out.relative_to(ROOT / 'build')
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'guest': 'not_run', 'commands': [],
              'sources': {name: sha_file(ROOT / name) for name in SOURCE_NAMES}}

    def run(command, name):
        command = list(map(str, command))
        report['commands'].append(command)
        with (out / (name + '.log')).open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        release = load_json(FROZEN_RELEASE)
        sdk = frozen / 'extracted/xylophoneos_revival_0.0.1-1024_sdk'
        media = frozen / 'extracted/xylophoneos_revival_0.0.1-1024_images'
        sdk_archive = frozen / 'xylophoneos_revival_0.0.1-1024_sdk.tar.gz'
        images_archive = frozen / 'xylophoneos_revival_0.0.1-1024_images.tar.gz'
        boot, published = media / 'xos.img', media / 'work_disk.img'
        sdk_digest = verify_release_file(release, sdk_archive, '_sdk.tar.gz')
        images_digest = verify_release_file(release, images_archive, '_images.tar.gz')
        boot_digest = verify_release_file(release, boot, '_boot.img')
        sdk_binding = inspect_sdk('newlib', sdk)
        published_digest = sha_file(published)
        with tarfile.open(images_archive, 'r:gz') as archive:
            members = [member for member in archive.getmembers() if member.name.endswith('/work_disk.img')]
            require(len(members) == 1 and members[0].isfile(), 'released archive lacks one regular work disk')
            require(members[0].size == published.stat().st_size, 'unpacked published disk size differs')
            with archive.extractfile(members[0]) as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == published_digest,
                        'unpacked work disk differs from the verified release archive')
        input_hashes = {str(path): sha_file(path) for path in (sdk_archive, images_archive, boot, published)}
        report.update(frozen_release=release['tag'], frozen_build_id=release['system_build_id'],
                      release_source_commit=release['source_commit'], sdk_binding=sdk_binding,
                      input_artifacts=input_hashes, sdk_archive_sha256=sdk_digest,
                      images_archive_sha256=images_digest, boot_sha256=boot_digest,
                      published_disk_sha256=published_digest, profile_sha256=sha_file(FROZEN_PROFILE))
        project = out / 'project'
        tool = [sys.executable, ROOT / 'scripts/xos_app.py', '--profile', FROZEN_PROFILE]
        run([*tool, 'init', project, '--id', 'rollback.frozen1024', '--language', 'c'], 'init')
        shutil.copyfile(ROOT / 'tests/fixtures/sdk_rollback/frozen.c', project / 'src/main.c')
        metadata = load_json(project / 'xos_app.json')
        metadata['required_features'].append('file_io')
        (project / 'xos_app.json').write_bytes(canonical(metadata))
        run([*tool, 'build', project, '--sdk', sdk], 'build')
        run([*tool, 'check', project, '--sdk', sdk], 'check')
        package = out / 'frozen1024.xpk'
        run([*tool, 'pack', project, '--sdk', sdk, '--output', package], 'pack')
        application = executable(package, FROZEN_PROFILE, '/usr/bin/frozen1024')
        seed = out / 'released_copy.img'
        sparse_copy(published, seed)
        require(sha_file(seed) == published_digest, 'working copy differs from the original release disk')
        disk = out / 'frozen_work.img'
        run([sys.executable, ROOT / 'scripts/xypm.py', 'install', package, '--profile', FROZEN_PROFILE,
             '--offline', '--image', seed, '--output-image', disk], 'install')
        require(sha_file(seed) == published_digest, 'package installation changed the input release copy')
        seed.unlink()
        scratch = out / 'seed.txt'
        seed_disk(disk, scratch, SEED)
        require(readback(disk, '/state/user.txt', out / 'readback.txt') == SEED, 'seeded user data differs')
        require(hashlib.sha256(readback(disk, '/usr/bin/frozen1024', out / 'readback.elf')).hexdigest()
                == application['elf_sha256'], 'installed new frozen fixture differs from its package')
        run([sys.executable, ROOT / 'scripts/xypm.py', 'verify-installed', '--profile', FROZEN_PROFILE,
             '--image', disk], 'verify_installed')
        require(inspect_sdk('newlib', sdk) == sdk_binding, 'frozen SDK changed while building')
        require(all(sha_file(Path(path)) == digest for path, digest in input_hashes.items()),
                'an original published artifact changed')
        require(report['sources'] == {name: sha_file(ROOT / name) for name in SOURCE_NAMES}, 'fixture input source changed')
        report.update(status='prepared_guest_not_run', application=application,
                      artifacts={name: sha_file(out / name) for name in ('frozen1024.xpk', 'frozen_work.img')},
                      project='project', disk='frozen_work.img', package='frozen1024.xpk',
                      user_seed=SEED.decode(), boot=str(boot), sdk=str(sdk), frozen_directory=str(frozen))
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS prepared newly built frozen 1024 fixture; guest not run')


if __name__ == '__main__':
    main()
