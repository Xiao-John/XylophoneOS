# SPDX-License-Identifier: Apache-2.0
"""Record explicit inputs of an Open Adventure build; this is not an attestation."""
import argparse
from pathlib import Path
import sys

from xos_app import sdk_check
from xypm_format import DEFAULT_PROFILE, canonical, load_json, require, sha_file

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/adventure'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--generated-c', type=Path, required=True)
    parser.add_argument('--generated-h', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    parser.add_argument('--build-environment', required=True,
                        help='actual build system, image identity and build procedure')
    parser.add_argument('--compiler', required=True,
                        help='actual compiler identity, version and relevant seed receipt')
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        lock = load_json(PORT / 'source_lock.json')
        profile = load_json(args.profile)
        sdk = sdk_check(args.sdk, profile)
        archive_hash = sha_file(args.archive)
        generated_c = sha_file(args.generated_c)
        generated_h = sha_file(args.generated_h)
        require(archive_hash == lock['sha256'], 'archive mismatch')
        require(generated_c == lock['data_sha256']['dungeon.c'] and
                generated_h == lock['data_sha256']['dungeon.h'], 'generated data mismatch')
        inputs = {'adventure.yaml': PORT / 'adventure.yaml', 'yaml.py': PORT / 'xos/yaml.py',
                  'xos_readline.cpp': PORT / 'xos_readline.cpp',
                  'readline.h': PORT / 'include/editline/readline.h',
                  'patch': PORT / 'patches/0001_xos_runtime.patch', 'build.sh': PORT / 'build.sh'}
        receipt = {'format_version': 1, 'target_profile': profile['id'],
                   'sdk_tree_sha256': sdk['tree_sha256'], 'output_sha256': sha_file(args.elf),
                   'upstream_archive_sha256': archive_hash, 'generated_dungeon_sha256': generated_c,
                   'generated_header_sha256': generated_h,
                   'port_inputs': {name: sha_file(path) for name, path in inputs.items()},
                   'build_environment': args.build_environment, 'compiler': args.compiler,
                   'provenance_scope': 'input hashes observed after build; environment and linkage supplied by operator, not independently verified'}
        protected = [args.elf, args.generated_c, args.generated_h, args.archive, args.profile, *inputs.values()]
        require(all(args.output.resolve() != path.resolve() for path in protected),
                'receipt output must not overwrite an input')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as output:
            output.write(canonical(receipt))
        print(args.output)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('open-adventure-receipt: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
