#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage a relocatable XOS glibc application SDK from a verified candidate."""
import argparse
import json
from pathlib import Path
import shutil

from xos_app import tree_receipt
from xypm_format import require, sha_file
from xypm_sdk_profile import metadata_snapshot, relative_file, verify_profile


ROOT = Path(__file__).resolve().parents[1]
APP_TOOLS = (
    'archive_member_map.py', 'build_glibc_program.py', 'glibc_g1_deps.py',
    'glibc_g1_probe.py', 'verify_glibc_source.py', 'xos_app.py', 'xypm_format.py',
    'xypm_sdk_profile.py',
)
LAUNCHER = '''#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import argparse
import os
from pathlib import Path
import sys

kit = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Use this kit to build XOS applications.')
parser.add_argument('command', choices=('init', 'build', 'check', 'pack'))
parser.add_argument('arguments', nargs=argparse.REMAINDER)
selection = parser.parse_args()
# Also disallow argparse's abbreviated forms of these fixed options.
for argument in selection.arguments:
    if argument == '--':
        break
    name = argument.split('=', 1)[0]
    if name.startswith('--') and any(flag.startswith(name) for flag in ('--profile', '--sdk')):
        parser.error('the kit supplies its own SDK and profile')

command = [sys.executable, str(kit / 'scripts/xos_app.py'),
           '--profile', str(kit / 'profile.json'), selection.command]
if selection.command != 'init':
    command += ['--sdk', str(kit / 'sdk')]
os.execv(sys.executable, command + selection.arguments)
'''
README = '''# XOS glibc application SDK

The archive contains a static glibc sysroot, profile, source verification
records, and application tools. The SDK can be moved as one directory.
Use Python 3.11 or newer and the cross tools recorded in `sdk/manifest.json`
on PATH. The application tools check the compiler, assembler, and linker
against those records on each build.

```sh
kit=/path/to/xos-glibc-sdk
"$kit/xos-app" init ./hello --id example.hello --language c
"$kit/xos-app" build ./hello
"$kit/xos-app" check ./hello
"$kit/xos-app" pack ./hello --output ./hello.xpk
```

Use `--language cpp` when the included profile supports C++. Keep projects and
package disks separate for each profile. The launcher selects this SDK for
one invocation. Use the existing frozen SDK and matching profile to resume
building or maintaining newlib projects and their package disks.
'''


def package_sdk(build, profile_path, output):
    require(not build.is_symlink(), 'SDK root symlink rejected')
    build = build.resolve(strict=True)
    output = output.absolute()
    require(output.resolve() != build and build not in output.resolve().parents,
            'kit output must be outside the SDK build')
    profile, profile_digest = metadata_snapshot(profile_path)
    binding = verify_profile(profile, 'glibc', build)
    output.mkdir(parents=True, exist_ok=False)
    try:
        sdk = output / 'sdk'
        shutil.copytree(build / 'sysroot', sdk / 'sysroot', symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '.cache', '*.pyc'))
        shutil.copyfile(relative_file(build, 'manifest.json'), sdk / 'manifest.json')
        sdk_binding = profile['sdk_binding']
        sources = [sdk_binding['source_authentication']]
        if sdk_binding['cxx_runtime']:
            sources.append(sdk_binding['cxx_runtime']['source_authentication'])
        for source in sources:
            for name in source['verification_files']:
                destination = sdk / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(relative_file(build, name), destination)
        shutil.copyfile(profile_path, output / 'profile.json')
        require(sha_file(output / 'profile.json') == profile_digest,
                'profile changed while staging the kit')
        require(verify_profile(profile, 'glibc', sdk) == binding,
                'SDK binding changed while staging the kit')
        tools = output / 'scripts'
        tools.mkdir()
        for name in APP_TOOLS:
            shutil.copyfile(ROOT / 'scripts' / name, tools / name)
        for name in ('LICENSE', 'NOTICE'):
            shutil.copyfile(ROOT / name, output / name)
        (output / 'README.md').write_text(README)
        launcher = output / 'xos-app'
        launcher.write_text(LAUNCHER)
        launcher.chmod(0o755)
        digest, _ = tree_receipt(output)
    except BaseException:
        shutil.rmtree(output)
        raise
    return {**binding, 'status': 'kit_staged', 'kit': str(output), 'kit_tree_sha256': digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-build', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='new directory outside the SDK build')
    args = parser.parse_args()
    try:
        result = package_sdk(args.sdk_build, args.profile, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'glibc SDK kit: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
