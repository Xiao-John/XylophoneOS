#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create or verify an isolated, unqualified newlib/glibc xypm SDK candidate."""
import argparse
import json
from pathlib import Path

from xypm_format import load_json, require
from xypm_repository import write_metadata
from xypm_sdk_profile import candidate_profile, verify_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify'))
    parser.add_argument('--runtime-family', choices=('newlib', 'glibc'), required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--sdk', type=Path, help='complete newlib SDK directory')
    source.add_argument('--sdk-build', type=Path, help='glibc build containing manifest.json and sysroot/')
    parser.add_argument('--id', dest='profile_id')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile', type=Path, help='candidate to verify')
    parser.add_argument('--cxx', action='store_true')
    parser.add_argument('--feature', action='append', default=[])
    args = parser.parse_args()
    if (args.runtime_family == 'glibc') != (args.sdk_build is not None):
        parser.error('glibc requires --sdk-build; newlib requires --sdk')
    location = args.sdk_build or args.sdk
    try:
        if args.action == 'verify':
            require(args.profile and not args.profile_id and not args.output and not args.cxx and not args.feature,
                    'verify accepts --profile and an SDK location only')
            result = verify_profile(load_json(args.profile), args.runtime_family, location)
        else:
            require(args.profile_id and args.output and not args.profile, 'create requires --id and --output')
            require(not args.output.exists() and not args.output.is_symlink(), 'profile output already exists')
            require(not location.is_symlink(), 'SDK root symlink rejected')
            output = args.output.resolve()
            root = location.resolve(strict=True)
            require(output != root and root not in output.parents, 'profile output must be outside the SDK')
            profile = candidate_profile(args.runtime_family, root, args.profile_id,
                                        cxx=args.cxx, features=args.feature)
            output.parent.mkdir(parents=True, exist_ok=True)
            write_metadata(output, profile)
            result = {'status': profile['status'], 'profile_id': profile['id'],
                      'runtime_family': profile['runtime_family'],
                      'sdk_tree_sha256': profile['sdk_binding']['sdk_tree_sha256']}
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'xypm profile: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
