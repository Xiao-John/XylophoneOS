# SPDX-License-Identifier: Apache-2.0
"""XYPM: host packages and explicit offline candidate-image transactions."""
import argparse
import json
from pathlib import Path
import sys
import subprocess
from xypm_format import (DEFAULT_PROFILE, PackageError, check_profile, load_json,
                         pack_package, verify_package)


def main(argv=None, *, require_initialized_image=False):
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
    command = sub.add_parser('repo-create', help='create a local content-addressed repository')
    command.add_argument('packages', nargs='+', type=Path)
    command.add_argument('-o', '--output', required=True, type=Path)
    command.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    command = sub.add_parser('repo-lock', help='lock explicit root package SHA-256 values')
    command.add_argument('repository', type=Path)
    command.add_argument('roots', nargs='+')
    command.add_argument('-o', '--output', required=True, type=Path)
    command.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
    for name in ('repo-verify', 'repo-plan', 'repo-install', 'repo-upgrade'):
        command = sub.add_parser(name)
        command.add_argument('repository', type=Path)
        command.add_argument('lock', type=Path)
        command.add_argument('--lock-sha256', help='independently trusted digest of the lock bytes')
        command.add_argument('--profile', type=Path, default=DEFAULT_PROFILE)
        if name in ('repo-install', 'repo-upgrade'):
            command.add_argument('id', help='one selected package; install dependencies in lock order')
            command.add_argument('--image', type=Path, required=True)
            command.add_argument('--output-image', type=Path, required=True)
            command.add_argument('--offline', action='store_true', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command.startswith('repo-'):
            from xypm_repository import (create_repository, make_lock, transact_locked,
                                        verify_repository, write_metadata)
            profile = load_json(args.profile)
            if args.command == 'repo-create':
                result = create_repository(args.packages, args.output, profile)
            elif args.command == 'repo-lock':
                lock = make_lock(args.repository, args.roots, profile)
                result = dict(lock, lock_sha256=write_metadata(args.output, lock))
            elif args.command in ('repo-install', 'repo-upgrade'):
                result = transact_locked(args.repository, args.lock, args.id, args.image,
                                         args.output_image, profile, args.command[5:],
                                         args.lock_sha256, require_initialized=require_initialized_image)
            else:
                result = verify_repository(args.repository, args.lock, profile, args.lock_sha256)
                if args.command == 'repo-plan':
                    result['transaction_scope'] = 'one explicit package per install/upgrade; dependencies first'
        elif args.command in ('install','upgrade','remove'):
            from xypm_image import transact
            result=transact(args.image,args.output_image,load_json(args.profile),args.command,
                            package=args.target if args.command!='remove' else None,
                            package_id=args.target if args.command=='remove' else None,
                            expected_sha256=getattr(args,'sha256',None),
                            require_initialized=require_initialized_image)
        elif args.command in ('list','info','verify-installed'):
            from xypm_image import query_image
            result=query_image(args.image,load_json(args.profile),args.command,getattr(args,'id',None),
                               require_initialized=require_initialized_image)
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
