# SPDX-License-Identifier: Apache-2.0
"""Target only the recorded E08-3 S2 failure, using a copy of its saved image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import command, resources


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-image', type=Path, required=True)
    parser.add_argument('--seed-manifest', type=Path)
    parser.add_argument('--position-only', action='store_true')
    args = parser.parse_args()
    if not args.position_only and not args.seed_manifest:
        parser.error('--seed-manifest required for archive final-link regression')
    build = ROOT / 'build'
    system = json.loads((build / 'manifest.json').read_text())
    report = {'status': 'failed', 'build_id': system['build_id'],
              'xos_sha256': sha(build / 'xos.img'), 'case_sha256': sha(args.case_image),
              'commands': [], 'checks': []}
    guest = None
    report_path = build / ('file_position_regression_report.json' if args.position_only
                           else 'archive_link_regression_report.json')
    try:
        with tempfile.TemporaryDirectory(prefix='xos_archive_fix_') as folder:
            base = Path(folder)
            disk = base / 'case.img'
            shutil.copyfile(args.case_image, disk)
            transfer(disk, 'import', '/bin/position_probe.elf', build / 'user_runtime_probe.image.elf')
            report['probe_sha256'] = sha(build / 'user_runtime_probe.image.elf')
            if args.seed_manifest:
                seed_path = args.seed_manifest.resolve()
                seed = json.loads(seed_path.read_text())
                sdk = ROOT / seed['sdk_manifest']
                if sha(sdk) != seed['sdk_manifest_sha256']:
                    raise AssertionError('SDK provenance changed')
                for name in ('crt0_posix.o', 'lib/libxos.a', 'lib/libxos_loader.a', 'lib/libc.a', 'lib/libm.a', 'user.ld'):
                    if sha(sdk.parent / name) != sha(build / 'sdk' / name):
                        raise AssertionError(f'Seed needs relink: {name}')
                report['seed_manifest'] = str(seed_path.relative_to(ROOT))
                report['seed_manifest_sha256'] = sha(seed_path)
                for name in ('ld', 'strip'):
                    item = seed['tools'][name]
                    tool = seed_path.parent / 'install' / item['path']
                    if sha(tool) != item['sha256']:
                        raise AssertionError(f'Seed changed: {name}')
                    transfer(disk, 'import', '/bin/fixed_' + name, tool)
            originals = {}
            for i, path in enumerate(('/out/s/libscale.a', '/out/s/start.o', '/src/app.ld')):
                output = base / f'before_{i}'
                transfer(disk, 'export', path, output)
                originals[path] = sha(output)
            report['inputs_sha256'] = originals
            guest = boot(disk, 'archive_link_regression')
            baseline = resources(guest)
            report['baseline'] = baseline

            def run(line, expected=0):
                output = command(guest, line, b'[wait] pid=', timeout=180)
                match = re.search(rb'kind=exited code=(-?\d+)', output)
                current = resources(guest)
                report['commands'].append({'line': line, 'output': output.decode(errors='replace'),
                                           'resources': current})
                if not match or int(match[1]) != expected:
                    raise AssertionError(f'{line}: {output[-2000:]!r}')
                if current != baseline:
                    raise AssertionError(f'resource drift: {current} != {baseline}')

            run('exec-file /bin/position_probe.elf file-position')
            report['checks'].append('raw_dup_buffered_append_positions')
            if not args.position_only:
                run('exec-file /bin/fixed_ld -T /src/app.ld -o /out/s/regression.elf /out/s/start.o /out/s/libscale.a')
                run('exec-file /out/s/regression.elf', 42)
                run('exec-file /bin/fixed_strip -o /out/s/regression_stripped.elf /out/s/regression.elf')
                run('exec-file /out/s/regression_stripped.elf', 42)
                report['checks'].append('saved_34_member_archive_final_link_execute_strip_execute')
            command(guest, 'sync', b'[files] sync=ok')
            guest.close()
            guest = None
            for i, (path, expected) in enumerate(originals.items()):
                output = base / f'after_{i}'
                transfer(disk, 'export', path, output)
                if sha(output) != expected:
                    raise AssertionError(f'input changed: {path}')
            report['checks'].append('inputs_preserved_resources_restored')
            if not args.position_only:
                report['outputs'] = {}
                for name in ('regression.elf', 'regression_stripped.elf'):
                    output = build / ('s2_fix_' + name)
                    transfer(disk, 'export', '/out/s/' + name, output)
                    report['outputs'][output.name] = sha(output)
            report['status'] = 'passed'
            print(f"PASS: {len(report['checks'])} targeted checks | build {system['build_id']}")
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        report_path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
