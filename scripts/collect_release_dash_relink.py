#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect the object files and ordered static link inputs for a released Dash."""

import argparse
from pathlib import Path, PurePosixPath
import shlex
import shutil
from tempfile import TemporaryDirectory

from relink_release_xypm import DASH_FORMAT
from xos_app import sdk_notices
from xos_bundle import TYPE_DASH, parse
from xypm_format import canonical, confined, load_json, require, sha_file

ROOT = Path(__file__).resolve().parents[1]
LINK_OPTIONS = ('-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096')
STARTUP = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')
BRIDGE = ('console_xos.o', 'syscall.o')
LIBRARIES = ('libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a')
FINISH = ('crtend.o', 'crtn.o')


def link_inputs(log, receipt, work, sysroot):
    compiler = receipt['target_tools']['gcc']['path']
    commands = [shlex.split(line) for line in log.read_text().splitlines()
                if line.startswith(compiler + ' ') and ' -o dash ' in line]
    require(len(commands) == 1, 'expected the configured Dash final make link')
    command = commands[0]
    prefix = next(word.removeprefix('-B') for word in command if word.startswith('-B'))
    recorded_work = PurePosixPath(prefix).parent
    recorded_sdk = PurePosixPath(next(word.removeprefix('--sysroot=') for word in command
                                     if word.startswith('--sysroot=')))
    require(PurePosixPath(prefix).name == 'target_tools' and recorded_work.name == work.name
            and recorded_work.is_absolute() and recorded_sdk.is_absolute(), 'unexpected configured build paths')

    def sdk_paths(names):
        return [str(recorded_sdk / 'usr/lib' / name) for name in names]

    pre_link = [*LINK_OPTIONS, '-T', str(recorded_sdk / 'user.ld'), *sdk_paths(STARTUP), '-o', 'dash']
    post_link = [*(str(recorded_work / name) for name in BRIDGE), '-Wl,--start-group',
                 *sdk_paths(LIBRARIES), '-Wl,--end-group', *sdk_paths(FINISH)]
    index = command.index(LINK_OPTIONS[0])
    require(command[index:index + len(pre_link)] == pre_link and command[-len(post_link):] == post_link,
            'configured make link changed')
    objects = command[index + len(pre_link):-len(post_link)]
    require(objects and 'main.o' in objects and len(objects) == len(set(objects))
            and all(PurePosixPath(name).suffix == '.o'
                    and PurePosixPath(name).parent.as_posix() in ('.', 'bltin') for name in objects),
            'unexpected Dash object list')

    sources = {}

    def sdk_file(name):
        path = confined(sysroot, name)
        require(sha_file(path) == receipt['inputs']['sdk/' + name], 'link input differs from Dash receipt: ' + name)
        destination = 'sysroot/' + name
        sources[destination] = path
        return {'file': destination}

    def object_file(name, path):
        destination = 'objects/' + name
        require(destination not in sources, 'duplicate Dash object: ' + name)
        sources[destination] = confined(work, path)
        return {'file': destination}

    plan = [*LINK_OPTIONS, '-T', sdk_file('user.ld'),
            *(sdk_file('usr/lib/' + name) for name in STARTUP),
            *(object_file(name, 'build/src/' + name) for name in objects),
            *(object_file(name, name) for name in BRIDGE),
            '-Wl,--start-group', *(sdk_file('usr/lib/' + name) for name in LIBRARIES),
            '-Wl,--end-group', *(sdk_file('usr/lib/' + name) for name in FINISH)]
    return plan, sources


def collect(args):
    release_path = args.release / 'release_manifest.json'
    require(sha_file(release_path) == args.release_sha256, 'selected release manifest differs')
    release = load_json(release_path)
    install_path = args.release / 'images/install_manifest.json'
    require(sha_file(install_path) == release['installer_manifest_sha256'], 'installer manifest differs')
    image = args.release / 'images/xos-install-dash.iso'
    require(sha_file(image) == release['installer_iso']['sha256'], 'installer ISO differs')
    install = load_json(install_path)
    bundle = install['boot_bundle']
    require(sha_file(args.bundle) == install['dash_sha256'] == bundle['container_sha256'],
            'installer bundle differs')
    dash, = (item for item in parse(args.bundle.read_bytes())['members'] if item['type'] == TYPE_DASH)
    require(dash['name'] == 'dash' and dash['sha256'].hex() == release['dash_sha256'],
            'actual bundle Dash differs')
    receipt_path = confined(args.work, 'manifest.json')
    require(sha_file(receipt_path) == args.dash_receipt_sha256, 'configured build receipt differs')
    receipt = load_json(receipt_path)
    require(receipt['profile'] == 'dash_glibc_preview' and receipt['load_segments_unchanged']
            and sha_file(confined(args.work, 'build/src/dash.runtime'))
            == sha_file(confined(args.work, 'build/src/dash'))
            == receipt['sha256'] == receipt['debug_sha256'] == release['dash_sha256'],
            'configured build did not reproduce the exact shipped Dash')
    require(receipt['bytes'] == dash['data_len'], 'Dash member length differs')
    sdk = args.release / 'application-sdk/sdk'
    profile_path = sdk.parent / 'profile.json'
    sdk_manifest_path = sdk / 'manifest.json'
    binding = release['application_sdk']
    require(sha_file(sdk_manifest_path) == receipt['sdk_manifest_sha256'] == binding['sdk_manifest_sha256']
            and sha_file(profile_path) == receipt['sdk_profile_binding']['profile_sha256']
            == binding['profile_file_sha256'], 'configured build uses another release SDK')

    plan, sources = link_inputs(args.make_log, receipt, args.work, sdk / 'sysroot')
    for path, name in sdk_notices(sdk, load_json(profile_path), 'c'):
        require(sha_file(path) == receipt['inputs']['sdk/' + name], 'SDK notice differs: ' + name)
        sources['licenses/' + name] = path
    for name in ('README.md', 'source_lock.json', 'upstream/COPYING'):
        source_name = 'src/ports/dash/' + name
        source = confined(ROOT, source_name)
        require(sha_file(source) == receipt['inputs'][source_name], 'Dash notice or source lock differs: ' + name)
        sources['dash/' + name] = source
    for name in ('relink_release_xypm.py', 'glibc_g1_probe.py', 'glibc_g1_deps.py', 'xypm_format.py'):
        sources['tools/' + name] = ROOT / 'scripts' / name
    sources.update({'receipt/release_manifest.json': release_path, 'receipt/install_manifest.json': install_path,
                    'receipt/dash.json': receipt_path, 'receipt/sdk_manifest.json': sdk_manifest_path,
                    'receipt/profile.json': profile_path})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    require(not args.output.exists() and not args.output.is_symlink(), 'choose absent materials output')
    with TemporaryDirectory(dir=args.output.parent) as temp:
        stage = Path(temp) / 'materials'
        files = {}
        for name, source in sorted(sources.items()):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            files[name] = sha_file(target)
        manifest = {'format': DASH_FORMAT, 'plan': plan, 'reference': release['dash_sha256'], 'files': files,
                    'tools': {name: receipt['target_tools'][name]['sha256'] for name in ('gcc', 'as', 'ld')}}
        (stage / 'manifest.json').write_bytes(canonical(manifest))
        stage.rename(args.output)
    print(sha_file(args.output / 'manifest.json'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('release', 'bundle', 'work', 'make-log', 'output'):
        parser.add_argument('--' + flag, required=True, type=Path)
    for flag in ('release-sha256', 'dash-receipt-sha256'):
        parser.add_argument('--' + flag, required=True)
    collect(parser.parse_args())


if __name__ == '__main__':
    main()
