# SPDX-License-Identifier: Apache-2.0
"""Exercise release input refusal and private transaction cleanup using actual XPKs."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import package_glibc_release as composition
from make_work_disk import create_fat32
from package_release import prepare_daily_package
from xypm_format import canonical, load_json, require, sha_file
from xypm_image import query_image, transact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'kit', 'cpython', 'wheel', 'foreign-wheel', 'other-daily', 'old-python', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    check_root = ROOT / 'build/releases'
    check_root.mkdir(parents=True, exist_ok=True)
    originals = (args.candidate / 'candidate_manifest.json', args.kit / 'profile.json', args.cpython,
                 args.wheel, args.foreign_wheel, args.other_daily, args.old_python)
    checksums = [sha_file(path) for path in originals]
    paths, proof = composition.inspect_candidate(args.candidate, args.kit)
    profile = load_json(args.kit / 'profile.json')
    daily = paths['stock/daily.xpk']
    results = {}

    with tempfile.TemporaryDirectory(prefix='.glibc_preflight_', dir=check_root) as temporary:
        work = Path(temporary)
        def reject(name, expected, *, candidate=args.candidate, cpython=args.cpython, wheel=args.wheel, extra=()):
            output = work / name
            result = subprocess.run(
                [sys.executable, ROOT / 'scripts/package_release.py', '--glibc-candidate', candidate,
                 '--glibc-app-kit', args.kit, '--cpython-package', cpython, '--wheel-package', wheel,
                 '--release-dir', output, *extra], capture_output=True, text=True)
            require(result.returncode == 1 and expected in result.stderr and not output.exists(),
                    'unexpected result for ' + name + ': ' + result.stderr)
            results[name] = result.stderr.strip()

        reject('foreign_wheel', 'package target profile mismatch', wheel=args.foreign_wheel)
        reject('other_same_profile_daily', 'daily XPK differs from the qualified installer',
               extra=('--daily-package', args.other_daily))
        reject('older_python_without_zlib', 'release requires the verified CPython zlib XPK',
               cpython=args.old_python)
        altered = work / 'tampered'
        for name, source in {'candidate_manifest.json': args.candidate / 'candidate_manifest.json', **paths}.items():
            target = altered / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (altered / 'stock_guest/report.json').write_text('{}\n')
        reject('changed_stock_certificate', 'candidate artifact differs: stock_guest/report.json', candidate=altered)

        output = work / 'failed_second_install'
        operations = []
        def interrupt(image, destination, selected, operation, **options):
            operations.append(options['package'].name)
            if len(operations) == 2:
                require(len(query_image(image, selected, 'list')['packages']) == 1,
                        'first private install did not commit')
                raise OSError('injected second install failure')
            return transact(image, destination, selected, operation, **options)
        with mock.patch.object(composition, 'transact', interrupt):
            try:
                composition.assemble(output, args.candidate, args.kit, daily, args.cpython, args.wheel, None)
            except OSError as error:
                require(str(error) == 'injected second install failure', 'unexpected transaction error')
            else:
                raise AssertionError('injected failure was not propagated')
        require(operations == ['daily.xpk', 'cpython.xpk'] and not output.exists(),
                'failed composition created a visible release')
        results['private_second_install_failure'] = 'committed private daily install discarded with entire staging'

        selected = composition.inspect_packages(profile, proof, daily, args.cpython, None)
        require(tuple(selected) == ('daily', 'cpython'), 'explicit glibc wheel omission changed package selection')
        results['optional_glibc_wheel'] = sorted(selected)
        try:
            prepare_daily_package(daily, args.kit / 'profile.json', args.kit / 'sdk', proof['system'], [], args.wheel)
        except ValueError as error:
            require('distinct profiles' in str(error), 'unexpected historical mixed profile result')
            results['historical_combined_path_guard'] = str(error)
        else:
            raise AssertionError('mixed packages accepted through historical path')
        legacy = load_json(ROOT / 'config/package/xos_x86_64_static_single_b2_v1.json')
        base = work / 'legacy-input.img'
        old_disk = work / 'legacy-wheel.img'
        create_fat32(base, 512)
        baseline = sha_file(base)
        transact(base, old_disk, legacy, 'install', package=args.foreign_wheel)
        require(sha_file(base) == baseline, 'legacy transaction wrote its input')
        results['historical_wheel_only_transaction'] = query_image(old_disk, legacy, 'verify-installed')
    require(checksums == [sha_file(path) for path in originals], 'a release input changed')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical({'status': 'passed', 'checks': results}))


if __name__ == '__main__':
    main()
