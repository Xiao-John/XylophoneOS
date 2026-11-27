#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the glibc release stages and freeze one bound, portable distribution."""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from package_application_preview import artifact
from package_glibc_release import MANIFEST, verify_assembled
from stage_glibc_release_supplements import (
    CHECKSUMS, CPYTHON_RELINK, DAILY_RELINK, DASH_RELINK, DISTRIBUTION,
    GNU_MAKE_RELINK, RELINK, SOURCES, SOURCES_MANIFEST, verify_base,
)
from xos_sdk import checked_binding, load_state, state_file
from xypm_format import MAX_MANIFEST, canonical, confined, require, sha_file, strict_json

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = 'pipeline_receipt.json'
STAGES = {
    'build': ('build_candidate.py', ('--output', '--glibc-app-kit', '--glibc-daily-source')),
    'package': ('package_release.py', ('--release-dir', '--glibc-candidate',
                                     '--glibc-app-kit', '--cpython-package')),
    'smoke': ('release_smoke.py', ('--glibc-release', '--output')),
    'components': ('package_glibc_release_sources.py', ()),
    'materials': ('stage_glibc_release_supplements.py', (
        '--release', '--components', '--xypm-relink', '--glibc-source', '--output',
        '--dash-relink', '--daily-relink', '--gnu-make-relink', '--cpython-relink')),
    'sdk': ('xos_sdk.py', ()),
    'application-preview': ('package_application_preview.py', ()),
}


def command(stage, arguments):
    """Return an argv vector; no shell or implicit legacy runtime selection."""
    script, required = STAGES[stage]
    if not any(arg in ('--help', '-h') for arg in arguments):
        options = [arg.partition('=')[0] for arg in arguments]
        for option in required:
            require(options.count(option) == 1, f'{stage} requires exactly one {option}')
        if stage == 'build':
            arguments = [*arguments, *(flag for flag in ('--guest', '--installer-guest')
                                       if flag not in options)]
    return [sys.executable, str(ROOT / 'scripts' / script), *arguments]


def checksum_bytes(records):
    return ''.join(f'{record["sha256"]}  {name}\n'
                   for name, record in sorted(records.items())).encode()


def flat_name(name):
    require(isinstance(name, str), 'distribution filename must be a string')
    path = PurePosixPath(name)
    require(path.name == name and name not in ('', '.', '..')
            and '\\' not in name and not any(ord(c) < 32 or ord(c) == 127 for c in name),
            'distribution asset must have a plain filename')
    return name


def bound_file(root, name, expected):
    flat_name(name)
    path = confined(root, name)
    require(path.is_file() and not path.is_symlink(), 'distribution asset must be a regular file: ' + name)
    require(artifact(path) == expected, 'distribution asset differs: ' + name)
    return path


def metadata_snapshot(path):
    with path.open('rb') as stream:
        data = stream.read(MAX_MANIFEST + 1)
    value = strict_json(data)
    require(isinstance(value, dict), 'release metadata must be an object')
    return value, {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def distribution_files(release_root, supplements_root):
    initial_release, manifest_record = metadata_snapshot(confined(release_root, MANIFEST))
    release, base = verify_base(release_root)
    require(release == initial_release and base[MANIFEST] == manifest_record,
            'release metadata changed while validating')
    supplement_path = confined(supplements_root, DISTRIBUTION)
    supplement, supplement_record = metadata_snapshot(supplement_path)
    require(supplement['format'] == 'xos_glibc_release_supplements_v6',
            'freeze requires the complete v6 static relink and source materials')
    require(supplement['release_manifest_sha256'] == base[MANIFEST]['sha256']
            and supplement['base_assets'] == base, 'supplements belong to a different release')
    source = supplement['glibc_source']['archive']
    expected = {SOURCES, SOURCES_MANIFEST, RELINK, DASH_RELINK,
                DAILY_RELINK, GNU_MAKE_RELINK, CPYTHON_RELINK, source}
    extra = supplement['supplements']
    require(set(extra) == expected and not set(extra) & set(base),
            'source and relink supplement inventory differs')
    records = {**base, **extra, DISTRIBUTION: supplement_record}
    require(confined(supplements_root, CHECKSUMS).read_bytes() == checksum_bytes(records),
            'supplement checksum list differs')
    paths = {name: bound_file(release_root, name, record) for name, record in base.items()}
    paths.update({name: bound_file(supplements_root, name, record) for name, record in extra.items()})
    paths[DISTRIBUTION] = bound_file(supplements_root, DISTRIBUTION, records[DISTRIBUTION])
    return release, paths, records


def smoke_files(root, release, digest):
    reports = {name: confined(root, name) for name in
               ('report.json', 'gnu_seed/report.json', 'combined_report.json')}
    snapshots = {name: metadata_snapshot(path) for name, path in reports.items()}
    package, seed, combined = (value[0] for value in snapshots.values())
    require(package['status'] == seed['status'] == combined['status'] == 'passed_subset',
            'package and native GNU smoke must both pass their declared subset')
    require(all(item['release_manifest_sha256'] == digest for item in (package, seed, combined)),
            'smoke belongs to a different release')
    require(package['assembled_disk_sha256'] == seed['initial_disk_sha256']
            == combined['work_disk_sha256'] == release['work_disk']['sha256'],
            'smoke used a different release disk')
    require(package['ordinary_iso_sha256'] == release['system']['iso']['sha256']
            and package['installer_iso_sha256'] == release['installer_iso']['sha256']
            and package['profile_sha256'] == release['application_sdk']['profile_sha256'],
            'smoke used a different image or profile')
    require(combined['packages_sha256'] == snapshots['report.json'][1]['sha256']
            and combined['gnu_seed_sha256'] == snapshots['gnu_seed/report.json'][1]['sha256']
            and combined['package_checks'] == package['checks']
            and combined['gnu_seed_cases'] == len(seed['cases'])
            and package['checks'] and seed['cases'], 'combined smoke binding differs')
    require(all(artifact(path) == snapshots[name][1] for name, path in reports.items()),
            'smoke report changed while validating')
    names = (
        ('package_smoke_report.json', 'report.json'),
        ('gnu_seed_smoke_report.json', 'gnu_seed/report.json'),
        ('combined_smoke_report.json', 'combined_report.json'))
    return ({name: reports[path] for name, path in names},
            {name: snapshots[path][1] for name, path in names})


def license_command(build, release):
    manifest = confined(build, 'manifest.json')
    require(sha_file(manifest) == release['system']['manifest_sha256'],
            'license build manifest differs from this release')
    return [sys.executable, str(ROOT / 'scripts/license_audit.py'), '--build', str(build)]


def sdk_bindings(path, release):
    state = load_state(state_file(path))
    require(state['active'] == 'glibc', 'select the bound glibc SDK before freezing')
    bindings = {family: {key: value for key, value in checked_binding(state, family).items()
                         if key != 'root'} for family in ('glibc', 'newlib')}
    require(bindings['glibc'] == release['application_sdk'],
            'selected glibc SDK differs from this release')
    return bindings


def publish_directory(source, destination):
    # The supported prerelease development environment is Linux. RENAME_NOREPLACE
    # closes the check/rename race without exposing an incomplete output directory.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, 'renameat2', None)
    require(rename is not None, 'atomic freeze requires Linux renameat2 support')
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), destination.name)


def freeze_files(output, paths, records, receipt):
    """Copy exact inputs into private staging, then publish the complete directory."""
    require(not output.exists() and not output.is_symlink(), 'choose a new frozen output directory')
    require(set(paths) == set(records) and not {CHECKSUMS, RECEIPT} & set(paths),
            'invalid frozen asset inventory')
    for name in paths:
        flat_name(name)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.release_freeze_', dir=output.parent) as temporary:
        staging = Path(temporary) / 'distribution'
        staging.mkdir()
        for name, source in paths.items():
            target = staging / name
            shutil.copyfile(source, target)
            require(artifact(target) == records[name], 'input changed while freezing: ' + name)
            with target.open('rb') as stream:
                os.fsync(stream.fileno())
        # Recheck all inputs, including those copied before another input changed.
        require(all(artifact(path) == records[name] for name, path in paths.items()),
                'distribution input changed during the freeze')
        (staging / RECEIPT).write_bytes(canonical(receipt))
        complete = {**records, RECEIPT: artifact(staging / RECEIPT)}
        (staging / CHECKSUMS).write_bytes(checksum_bytes(complete))
        for name in (RECEIPT, CHECKSUMS):
            with (staging / name).open('rb') as stream:
                os.fsync(stream.fileno())
        with_dir = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(with_dir)
        finally:
            os.close(with_dir)
        publish_directory(staging, output)
        parent = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    return complete


def freeze(args):
    release, paths, records = distribution_files(args.release, args.supplements)
    checked, _ = verify_assembled(args.release)
    require(checked == release, 'release changed while verifying the distribution')
    digest = records[MANIFEST]['sha256']
    bindings = sdk_bindings(args.sdk_state, release)
    smoke, smoke_records = smoke_files(args.smoke, release, digest)
    paths.update(smoke)
    records.update(smoke_records)
    receipt = {'format': 'xos_glibc_release_pipeline_v1', 'runtime_family': 'glibc',
               'status': 'assembled_static_distribution', 'release_manifest_sha256': digest,
               'sdk_bindings': bindings, 'assets': records,
               'qualification': 'existing_package_and_native_gnu_smoke_subset',
               'rollback': 'explicit_sdk_selection_with_independent_frozen_newlib_disk',
               'not_qualified': ['public_dynamic_application_startup', 'dynamic_generation_activation',
                                 'physical_power_loss', 'all_application_release_gates']}
    complete = freeze_files(args.output.absolute(), paths, records, receipt)
    print(json.dumps({'status': receipt['status'], 'assets': len(complete),
                      'release_manifest_sha256': digest}, indent=2))


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments and arguments[0] in STAGES:
        try:
            return subprocess.run(command(arguments[0], arguments[1:])).returncode
        except (OSError, ValueError) as error:
            print('glibc release pipeline: ' + str(error), file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False,
                                     epilog='Build/package/smoke/components/materials/sdk/application-preview '
                                            'forward to their bound tools. Use STAGE --help for arguments. '
                                            'Historical releases require release_pipeline.sh --newlib.')
    sub = parser.add_subparsers(dest='stage', required=True)
    for name in ('freeze', 'checksums'):
        step = sub.add_parser(name, allow_abbrev=False,
                              help='freeze all verified assets into one new directory')
        for flag in ('release', 'supplements', 'smoke', 'sdk-state', 'output'):
            step.add_argument('--' + flag, type=Path, required=True)
        step.set_defaults(run=freeze)
    for name in ('status', 'gates'):
        step = sub.add_parser(name, allow_abbrev=False)
        step.add_argument('--release', type=Path, required=True)
        if name == 'gates':
            step.add_argument('--build', type=Path, required=True,
                              help='exact system build recorded in this release')
    rollback = sub.add_parser('rollback', allow_abbrev=False,
                              help='explicitly select the already bound frozen newlib SDK')
    rollback.add_argument('--state', type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        if args.stage == 'rollback':
            return subprocess.run([sys.executable, str(ROOT / 'scripts/xos_sdk.py'),
                                   '--state', str(args.state), 'use', 'newlib']).returncode
        if args.stage in ('freeze', 'checksums'):
            args.run(args)
        else:
            release, _ = verify_assembled(args.release)
            if args.stage == 'gates':
                subprocess.run(license_command(args.build, release), check=True)
            print(json.dumps({'status': release['status'], 'runtime_family': 'glibc',
                              'build_id': release['system']['build_id'],
                              'application_sdk': release['application_sdk'],
                              'guest_qualification': 'run smoke for this exact release'}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('glibc release pipeline: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
