#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Select a bound application SDK and an independent frozen newlib rollback."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from build_candidate import inspect_app_kit
from package_application_preview import FROZEN_PROFILE, FROZEN_RELEASE
from xos_app import sdk_check
from xypm_format import canonical, fields, require
from xypm_repository import write_metadata
from xypm_sdk_profile import metadata_snapshot, relative_file

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / 'build/application_sdk_selection.json'
FAMILIES = ('glibc', 'newlib')


def inspect(family, root):
    require(root.is_dir() and not root.is_symlink(), 'SDK must be a real directory')
    root = root.resolve(strict=True)
    if family == 'glibc':
        binding = inspect_app_kit(root)
    else:
        profile, profile_hash = metadata_snapshot(FROZEN_PROFILE)
        release, _ = metadata_snapshot(FROZEN_RELEASE)
        frozen = sdk_check(root, profile)
        require(frozen['sdk_build_id'] == release['system_build_id']
                and frozen['sdk_build_id'] in profile['verified_system_builds'],
                'newlib SDK is not the frozen release')
        binding = {'profile_id': profile['id'], 'profile_sha256': profile_hash,
                   'sdk_tree_sha256': frozen['tree_sha256'],
                   'sdk_manifest_sha256': frozen['files']['manifest.json']}
    return {'root': str(root), **binding}


def state_file(path):
    require(not path.is_symlink(), 'SDK selection file must not be a symlink')
    return path.parent.resolve() / path.name


def load_state(path):
    require(path.is_file(), 'initialize an SDK selection with setup first')
    state, _ = metadata_snapshot(path)
    fields(state, ('format_version', 'active', 'bindings'))
    require(type(state['format_version']) is int and state['format_version'] == 1
            and state['active'] in FAMILIES, 'invalid SDK selection format')
    fields(state['bindings'], FAMILIES)
    return state


def setup(path, glibc_kit, newlib_sdk):
    bindings = {'glibc': inspect('glibc', glibc_kit), 'newlib': inspect('newlib', newlib_sdk)}
    glibc, newlib = (Path(bindings[family]['root']) for family in FAMILIES)
    require(glibc != newlib and not glibc.is_relative_to(newlib) and not newlib.is_relative_to(glibc),
            'glibc and newlib SDK roots must be independent')
    require(not path.is_relative_to(glibc) and not path.is_relative_to(newlib),
            'SDK selection file must be outside both SDKs')
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {'format_version': 1, 'active': 'glibc', 'bindings': bindings}
    write_metadata(path, state)
    return state


def checked_binding(state, family):
    binding = state['bindings'][family]
    current = inspect(family, Path(binding['root']))
    require(binding == current, f'the configured {family} SDK binding changed')
    return current


def select(path, state, family):
    checked_binding(state, family)
    if family == 'glibc':
        checked_binding(state, 'newlib')
    updated = {**state, 'active': family}
    if updated != state:
        fd, temporary = tempfile.mkstemp(prefix='.application_sdk_', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(canonical(updated))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return updated


def delegate(frontend, operation, arguments, state):
    for argument in arguments:
        if argument == '--':
            break
        option = argument.partition('=')[0]
        require(not option.startswith('--') or not any(flag.startswith(option) for flag in ('--profile', '--sdk')),
                'the SDK choice supplies its own --profile and --sdk')
    family = state['active']
    root = Path(checked_binding(state, family)['root'])
    profile = relative_file(root, 'profile.json') if family == 'glibc' else FROZEN_PROFILE
    if frontend == 'xypm':
        from xypm import main as xypm_main

        return xypm_main([operation, '--profile', str(profile), *arguments], require_initialized_image=True)
    sdk = root / 'sdk' if family == 'glibc' else root
    sdk_arguments = [] if operation == 'init' else ['--sdk', str(sdk)]
    command = [str(ROOT / 'scripts/xos_app.py'), '--profile', str(profile), operation, *sdk_arguments]
    return subprocess.run([sys.executable, *command, *arguments]).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    commands = parser.add_subparsers(dest='command', required=True)
    configure = commands.add_parser('setup', help='bind both SDKs and select glibc')
    configure.add_argument('--glibc-kit', type=Path, required=True)
    configure.add_argument('--newlib-sdk', type=Path, required=True)
    switch = commands.add_parser('use', help='switch between the already bound SDKs')
    switch.add_argument('family', choices=FAMILIES)
    commands.add_parser('status', help='show the verified active SDK and configured bindings')
    app = commands.add_parser('app', help='build applications using the active SDK')
    app.add_argument('operation', choices=('init', 'build', 'check', 'pack'))
    app.add_argument('arguments', nargs=argparse.REMAINDER)
    xypm = commands.add_parser('xypm', help='use the active profile for host package commands')
    xypm.add_argument('operation')
    xypm.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        path = state_file(args.state)
        if args.command == 'setup':
            state = setup(path, args.glibc_kit, args.newlib_sdk)
        else:
            state = load_state(path)
            if args.command in ('app', 'xypm'):
                return delegate(args.command, args.operation, args.arguments, state)
            if args.command == 'use':
                state = select(path, state, args.family)
            else:
                checked_binding(state, state['active'])
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('xos_sdk: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
