# SPDX-License-Identifier: Apache-2.0
"""Stage smaller glibc daily runtime ELFs and keep the full build for debugging."""
import argparse
from hashlib import sha256
import io
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from xypm_format import canonical, inspect_elf, load_json, require, sha_file, strict_json
from xypm_sdk_profile import GLIBC_STDIO_RECEIVER, metadata_snapshot, require_stdio_marker, verify_profile

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'src/ports/sbase/daily_utilities.json'



def loaded_image(data):
    # A LOAD can contain the ELF header. objcopy updates only the section-table
    # location, count and name-table index there. The loader's program headers
    # and the independently checked .xos.exec marker retain their meaning.
    contents = data[:40] + bytes(8) + data[48:60] + bytes(4) + data[64:]
    table = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    headers = data[table:table + stride * count]
    segments = []
    for offset in range(0, len(headers), stride):
        kind, _, start, _, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', headers, offset)
        if kind in (1, 7):  # PT_LOAD, PT_TLS
            segments.append(contents[start:start + size])
    return contents[:64], headers, segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--tools', type=Path, required=True, help='full glibc daily build')
    parser.add_argument('--output-dir', type=Path, required=True, help='new runtime-only directory')
    args = parser.parse_args()
    try:
        profile = load_json(args.profile)
        binding = verify_profile(profile, 'glibc', args.sdk)
        sdk_digest = profile['sdk_binding']['sdk_manifest_sha256']
        metadata, _ = metadata_snapshot(args.sdk / 'manifest.json', sdk_digest)
        require('stdio_transfer' in profile['features'], 'profile must bind a stdio receiver')
        receiver = profile['sdk_binding']['link_artifacts'][GLIBC_STDIO_RECEIVER]
        objcopy = shutil.which('x86_64-elf-objcopy')
        require(objcopy is not None, 'cross objcopy not found')
        objcopy_digest = metadata['tools']['x86_64-elf-objcopy']['sha256']
        require(sha_file(objcopy) == objcopy_digest, 'objcopy differs from SDK build')

        source = args.tools.resolve(strict=True)
        manifest = source / 'manifest.json'
        full = manifest.read_bytes()
        build = strict_json(full)
        require(build['runtime_family'] == 'glibc' and 'debug_stage' not in build and
                build['sdk_manifest_sha256'] == sdk_digest and
                build['profile_sha256'] == binding['profile_sha256'] and
                build['sdk_tree_sha256'] == binding['sdk_tree_sha256'] and
                build['stdio_receiver_sha256'] == receiver, 'full build does not match the glibc SDK/profile')
        names = [item['name'] for item in load_json(REGISTRY)['tools']]
        require([item['name'] for item in build['tools']] == names and
                build['registry_sha256'] == sha_file(REGISTRY) and
                build['builder_sha256'] == sha_file(ROOT / 'scripts/build_daily_utilities.py'),
                'full build differs from daily registry or builder')
        out = args.output_dir.absolute()
        require(not out.exists() and not out.is_symlink(), 'output must be a new directory')
        full_bytes, runtime_bytes = 0, 0
        with tempfile.TemporaryDirectory(prefix='.daily_runtime_', dir=out.parent) as folder:
            work = Path(folder)
            stage = work / 'runtime'
            stage.mkdir()
            captured = work / 'debug.elf'
            for item in build['tools']:
                name = item['name']
                original = source / name
                require(original.is_file() and not original.is_symlink(), 'invalid full ELF: ' + name)
                data = original.read_bytes()
                require(len(data) == item['size'] and sha256(data).hexdigest() == item['elf_sha256'],
                        'full ELF differs from its build receipt: ' + name)
                inspect_elf(io.BytesIO(data))
                require_stdio_marker(data, name)
                captured.write_bytes(data)
                output = stage / name
                subprocess.run([objcopy, '--strip-debug', str(captured), str(output)], check=True)
                runtime = output.read_bytes()
                layout = inspect_elf(io.BytesIO(runtime))
                require_stdio_marker(runtime, name)
                require(layout == item['elf_layout'] and loaded_image(data) == loaded_image(runtime),
                        'debug stripping changed the loaded image: ' + name)
                require(sha_file(original) == item['elf_sha256'], 'full ELF changed while staging: ' + name)
                item['debug_sha256'], item['debug_size'] = item['elf_sha256'], len(data)
                item['elf_sha256'], item['size'] = sha256(runtime).hexdigest(), len(runtime)
                full_bytes += len(data)
                runtime_bytes += len(runtime)
            require(manifest.read_bytes() == full and sha_file(objcopy) == objcopy_digest and
                    verify_profile(load_json(args.profile), 'glibc', args.sdk) == binding,
                    'full build, strip tool or SDK/profile changed while staging')
            build['debug_stage'] = {'builder_sha256': sha_file(__file__),
                                    'objcopy_sha256': objcopy_digest, 'mode': 'strip-debug',
                                    'original_manifest_sha256': sha256(full).hexdigest(),
                                    'full_bytes': full_bytes, 'runtime_bytes': runtime_bytes}
            (stage / 'manifest.json').write_bytes(canonical(build))
            stage.rename(out)
        print(canonical(build['debug_stage']).decode(), end='')
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('daily-runtime-stage: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
