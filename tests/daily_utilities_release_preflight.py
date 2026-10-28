# SPDX-License-Identifier: Apache-2.0
"""Exercise release preflight with a real XPK and frozen SDK; no release is produced."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from package_release import prepare_daily_package
from sdk_receipt import tree_receipt, verify_copied_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--system-sdk', type=Path)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--build-id', default='0babbb11032c9197')
    args = parser.parse_args()
    system = {'build_id':args.build_id}
    if args.system_sdk or args.runtime:
        assert args.system_sdk and args.runtime
        verify_copied_inputs(args.sdk, tree_receipt(args.system_sdk), tree_receipt(args.runtime))
        print('PASS composed sdk matches system and target runtime')
    profile, package = prepare_daily_package(args.package,args.profile,args.sdk,system,[],None)
    assert package['manifest']['id'] == 'xos.daily_utilities'
    assert len([x for x in package['manifest']['files'] if x['role']=='executable']) == 13
    def rejected(label, sdk=args.sdk, system=system, entries=None, wheel=None):
        try:
            prepare_daily_package(args.package,args.profile,sdk,system,entries or [],wheel)
        except (ValueError, OSError, KeyError):
            print('PASS',label)
            return
        raise AssertionError('expected rejection: '+label)
    rejected('wrong system',system={'build_id':'wrong'})
    rejected('mismatched sdk',sdk=ROOT/'build/utf8_filenames_qualified/sdk')
    rejected('unmanaged path collision',entries=[{'guest_path':'/usr/bin/ls'}])
    rejected('wheel profile not mixed',wheel=Path('wheel.xpk'))
    print('PASS actual package and sdk')

if __name__ == '__main__': main()
