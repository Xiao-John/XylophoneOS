# SPDX-License-Identifier: Apache-2.0
"""XYPM: host packages and explicit offline candidate-image transactions."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
from xypm_format import (DEFAULT_PROFILE, PackageError, check_profile, load_json,
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
    for name in ('install','upgrade','remove'):
        command=sub.add_parser(name)
        command.add_argument('target',help='package.xpk, or installed package ID for remove')
        command.add_argument('--image',type=Path,required=True)
        command.add_argument('--output-image',type=Path,required=True)
        command.add_argument('--offline',action='store_true',required=True,help='QEMU must be closed; export a new image')
        command.add_argument('--profile',type=Path,default=DEFAULT_PROFILE)
        if name!='remove':command.add_argument('--sha256')
    for name in ('list','info','verify-installed'):
        command=sub.add_parser(name)
        command.add_argument('--image',type=Path,required=True)
        command.add_argument('--profile',type=Path,default=DEFAULT_PROFILE)
        if name=='info':command.add_argument('id')
    args = parser.parse_args()
    try:
        if args.command in ('install','upgrade','remove'):
            from xypm_image import transact
            result=transact(args.image,args.output_image,load_json(args.profile),args.command,
                            package=args.target if args.command!='remove' else None,
                            package_id=args.target if args.command=='remove' else None,
                            expected_sha256=getattr(args,'sha256',None))
        elif args.command in ('list','info','verify-installed'):
            from xypm_image import query_image
            result=query_image(args.image,load_json(args.profile),args.command,getattr(args,'id',None))
        elif args.command == 'pack':
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
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print('xypm: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
