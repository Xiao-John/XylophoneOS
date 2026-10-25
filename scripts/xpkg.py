# SPDX-License-Identifier: Apache-2.0
"""Host XPK pack/inspect/verify tools. P0 does not install or execute packages."""
import argparse
import json
from pathlib import Path
import sys
from xpkg_format import (DEFAULT_PROFILE, PackageError, check_profile, load_json,
                         pack_package, verify_package)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'verify'):
        command = sub.add_parser(name)
        command.add_argument('package', type=Path)
        command.add_argument('--profile', type=Path)
        command.add_argument('--sha256')
    pack = sub.add_parser('pack')
    pack.add_argument('--root', type=Path, required=True)
    pack.add_argument('--manifest', type=Path, required=True)
    pack.add_argument('-o', '--output', type=Path, required=True)
    pack.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    try:
        if args.command == 'pack':
            manifest = load_json(args.manifest)
            check_profile(manifest, load_json(args.profile))
            result = pack_package(args.root, manifest, args.output)
        else:
            profile = load_json(args.profile) if args.profile else None
            result = verify_package(args.package, profile, args.sha256)
        if args.command == 'verify':
            result = {key: value for key, value in result.items() if key != 'manifest'}
            result['compatibility'] = 'profile_checked' if args.profile else 'not_checked'
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print('xpkg: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
