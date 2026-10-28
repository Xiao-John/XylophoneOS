# SPDX-License-Identifier: Apache-2.0
"""Compare host and guest P2 package validation on identical archive bytes."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from process_smoke import resources
from task_smoke import send_bytes, pump
from xypm_format import PackageError, canonical, load_json, require, sha_file, verify_package
from xypm_image import Disk, load_db, query_image, transact, validate_dependencies


def make_archive(path, manifest, bodies, manifest_bytes=None, extra=None):
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as archive:
        entries = [('manifest.json', manifest_bytes if manifest_bytes is not None else canonical(manifest))]
        entries += [('payload/' + item['path'], bodies[item['path']]) for item in manifest['files']]
        entries += extra or []
        for name, data in entries:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))


def fixtures(folder, profile, elf):
    bodies = {'usr/share/p2/data.txt': b'hello xypm\n',
              'usr/share/p2/LICENSE': b'fixture license\n',
              'usr/share/p2/receipt.json': b'{}\n'}
    def item(path, data, role='data'):
        return {'path': path, 'type': 'file', 'size': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'role': role}
    manifest = {'format_version': 1, 'id': 'friends.p2', 'upstream_version': '1.0',
                'revision': 2147483647, 'target_profile': profile['id'], 'required_features': [],
                'runtime_dependencies': [], 'files': [item(k, v) for k, v in bodies.items()],
                'licenses': ['usr/share/p2/LICENSE'],
                'build_receipt': {'path': 'usr/share/p2/receipt.json',
                                  'sha256': hashlib.sha256(b'{}\n').hexdigest()},
                'source': 'P2 acceptance fixture'}
    cases = []
    def add(name, good, m=manifest, files=bodies, raw=None, extra=None):
        path = folder / (name + '.xpk')
        make_archive(path, m, files, raw, extra)
        cases.append((name, path, good))
    add('valid', True)
    long_text = copy.deepcopy(manifest); long_text['upstream_version'] = '木' * 400
    add('unicode_version', True, m=long_text)
    wrong = copy.deepcopy(manifest); wrong['licenses'] = ['usr/share/p2/license']
    add('license_case', False, m=wrong)
    wrong = copy.deepcopy(manifest); wrong['build_receipt']['path'] = 'usr/share/p2/RECEIPT.JSON'
    add('receipt_case', False, m=wrong)
    add('duplicate_key', False, raw=canonical(manifest).replace(b'{', b'{"id":"friends.other",', 1))
    add('invalid_utf8', False, raw=canonical(manifest).replace(b'P2 acceptance fixture', b'bad\xff'))
    add('surrogate', False, raw=canonical(manifest).replace(b'P2 acceptance fixture', b'\\ud800'))
    add('float_number', False, raw=canonical(manifest).replace(b'"revision": 2147483647', b'"revision": 0.5'))
    wrong = copy.deepcopy(manifest); wrong['target_profile'] = 'wrong-profile'
    add('profile', False, m=wrong)
    wrong = copy.deepcopy(manifest); wrong['files'][0]['sha256'] = '0' * 64
    add('payload_hash', False, m=wrong)
    add('extra_member', False, extra=[('payload/usr/share/p2/extra', b'extra')])
    add('duplicate_member', False, extra=[('payload/usr/share/p2/data.txt', bodies['usr/share/p2/data.txt'])])
    wrong = copy.deepcopy(manifest); wrong['files'][0]['path'] = 'usr/share/p2/../bad'
    files = dict(bodies); files[wrong['files'][0]['path']] = files['usr/share/p2/data.txt']
    add('traversal', False, m=wrong, files=files)
    wrong = copy.deepcopy(manifest); wrong['files'][0]['path'] = 'usr/share/LONGDI~1/data.txt'
    files = dict(bodies); files[wrong['files'][0]['path']] = files['usr/share/p2/data.txt']
    add('fat_short_alias_syntax', False, m=wrong, files=files)
    executable = elf.read_bytes()
    elf_manifest = copy.deepcopy(manifest); elf_files = dict(bodies)
    elf_files['usr/bin/p2_sample'] = executable
    elf_manifest['files'].append(item('usr/bin/p2_sample', executable, 'executable'))
    add('elf_valid', True, m=elf_manifest, files=elf_files)
    bad_elf = bytearray(executable); struct.pack_into('<H', bad_elf, 18, 183)
    bad_manifest = copy.deepcopy(elf_manifest); bad_files = dict(elf_files)
    bad_files['usr/bin/p2_sample'] = bytes(bad_elf)
    bad_manifest['files'][-1] = item('usr/bin/p2_sample', bad_files['usr/bin/p2_sample'], 'executable')
    add('elf_machine', False, m=bad_manifest, files=bad_files)
    phoff = struct.unpack_from('<Q', executable, 32)[0]
    bad_elf = bytearray(executable); struct.pack_into('<I', bad_elf, phoff, 2)
    bad_files = dict(elf_files); bad_files['usr/bin/p2_sample'] = bytes(bad_elf)
    bad_manifest = copy.deepcopy(elf_manifest)
    bad_manifest['files'][-1] = item('usr/bin/p2_sample', bad_files['usr/bin/p2_sample'], 'executable')
    add('elf_dynamic', False, m=bad_manifest, files=bad_files)
    bad_elf = bytearray(executable); struct.pack_into('<Q', bad_elf, 24, 0)
    bad_files = dict(elf_files); bad_files['usr/bin/p2_sample'] = bytes(bad_elf)
    bad_manifest = copy.deepcopy(elf_manifest)
    bad_manifest['files'][-1] = item('usr/bin/p2_sample', bad_files['usr/bin/p2_sample'], 'executable')
    add('elf_entry', False, m=bad_manifest, files=bad_files)
    data = (folder / 'valid.xpk').read_bytes()
    for name, content in [('truncated', data[:1024]), ('bad_checksum', bytes([data[0] ^ 1]) + data[1:])]:
        path = folder / (name + '.xpk'); path.write_bytes(content); cases.append((name, path, False))
    link = bytearray(data); link[156] = ord('2'); link[148:156] = b' '*8
    link[148:156] = ('%06o' % sum(link[:512])).encode() + b'\0 '
    path = folder/'tar_link.xpk'; path.write_bytes(link); cases.append(('tar_link', path, False))
    dependent = copy.deepcopy(manifest); dependent['id'] = 'friends.dependent'
    dependent_files = {}
    for entry in dependent['files']:
        old = entry['path']; entry['path'] = old.replace('/p2/', '/dependent/')
        dependent_files[entry['path']] = bodies[old]
    dependent['licenses'] = ['usr/share/dependent/LICENSE']
    dependent['build_receipt']['path'] = 'usr/share/dependent/receipt.json'
    dependent['runtime_dependencies'] = [{'id': 'friends.p2', 'upstream_version': '1.0',
                                          'revision': 2147483647, 'sha256': sha_file(folder/'valid.xpk')}]
    plan_cases = []
    def add_plan(name, value, files):
        path = folder/(name+'.xpk'); make_archive(path, value, files)
        verify_package(path, profile); plan_cases.append((name, path))
    add_plan('dep_good', dependent, dependent_files)
    mismatch = copy.deepcopy(dependent); mismatch['runtime_dependencies'][0]['sha256'] = '0'*64
    add_plan('dep_bad', mismatch, dependent_files)
    collision = copy.deepcopy(dependent); old = collision['files'][0]['path']
    collision['files'][0]['path'] = 'usr/share/p2/data.txt'
    collision_files = dict(dependent_files); collision_files[collision['files'][0]['path']] = collision_files.pop(old)
    add_plan('owned_collision', collision, collision_files)
    unmanaged = copy.deepcopy(dependent); old = unmanaged['files'][0]['path']
    unmanaged['files'][0]['path'] = 'usr/share/unmanaged.txt'
    unmanaged_files = dict(dependent_files); unmanaged_files[unmanaged['files'][0]['path']] = unmanaged_files.pop(old)
    add_plan('unmanaged_collision', unmanaged, unmanaged_files)
    folded = copy.deepcopy(unmanaged); folded['files'][0]['path'] = 'usr/share/UNMANAGED.TXT'
    folded_files = dict(unmanaged_files); folded_files[folded['files'][0]['path']] = folded_files.pop('usr/share/unmanaged.txt')
    add_plan('case_collision', folded, folded_files)
    parent = copy.deepcopy(unmanaged); parent['files'][0]['path'] = 'usr/share/unmanaged.txt/child'
    parent_files = dict(unmanaged_files); parent_files[parent['files'][0]['path']] = parent_files.pop('usr/share/unmanaged.txt')
    add_plan('parent_file', parent, parent_files)
    return cases, plan_cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system', type=Path, required=True)
    parser.add_argument('--xypm-build', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT/'config/package/xos_x86_64_static_single_b2_v1.json')
    parser.add_argument('--dash-elf', type=Path)
    parser.add_argument('--dash-sha256')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    system = args.system.resolve(); system_manifest = load_json(system/'manifest.json')
    image = system/'xos.img'; require(sha_file(image) == system_manifest['artifacts']['xos.img']['sha256'], 'system image mismatch')
    build = load_json(args.xypm_build); elf = Path(build['elf']); profile = load_json(args.profile)
    report = {'status': 'failed', 'system_build_id': system_manifest['build_id'], 'image_sha256': sha_file(image),
              'xypm_elf_sha256': sha_file(elf), 'xypm_package_sha256': build['sha256'],
              'test_sha256': sha_file(Path(__file__)), 'profile_sha256': sha_file(args.profile),
              'dash_sha256': args.dash_sha256 if args.dash_elf else None,
              'profile': profile['id'], 'checks': [], 'cases': [],
              'not_run': ['guest_install_upgrade_remove', 'persistent_recovery', 'power_loss']}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xypm_p2_verify_') as temp:
            folder = Path(temp); cases, plan_cases = fixtures(folder, profile, elf)
            for name, path, good in cases:
                try:
                    verify_package(path, profile); host_ok = True
                except PackageError:
                    host_ok = False
                require(host_ok == good, 'fixture host expectation differs: ' + name)
                report['cases'].append({'name': name, 'sha256': sha_file(path), 'expected': good, 'host': host_ok})
            disk = folder/'work.img'; create_fat32(disk, 512)
            with Disk(disk, folder) as backend:
                for directory in ('/usr', '/usr/bin', '/usr/share', '/out', '/tests'):
                    backend.command('mkdir', directory)
                backend.command('import', '/usr/bin/xypm', elf)
                unmanaged = folder/'unmanaged'; unmanaged.write_bytes(b'user data')
                backend.command('import', '/usr/share/unmanaged.txt', unmanaged)
                if args.dash_elf:
                    require(args.dash_sha256 and sha_file(args.dash_elf) == args.dash_sha256, 'dash hash mismatch')
                    backend.command('import', '/usr/bin/dash', args.dash_elf)
                    script = folder/'dash_check.sh'
                    script.write_text('set -e\nxypm verify /out/valid.xpk > /out/dash_ok.txt\nxypm verify /out/payload_hash.xpk 2> /out/dash_error.txt || test "$?" -eq 3\nxypm plan upgrade /out/valid.xpk\n')
                    backend.command('import', '/tests/dash_check.sh', script)
                for name, path, _ in cases:
                    backend.command('import', '/out/'+name+'.xpk', path)
                for name, path in plan_cases:
                    backend.command('import', '/out/'+name+'.xpk', path)
            boot = folder/'boot.img'; shutil.copyfile(image, boot)
            guest = Guest(boot, 'package_p2_verify', work_disk=disk)
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest); report['baseline'] = baseline
            def command(line, expected):
                start = len(guest.output); send_bytes(guest, line.encode()+b'\r')
                guest.expect_supervisor(start=start, timeout=120)
                data = bytes(guest.output)[start:]
                statuses = re.findall(rb'kind=exited code=(-?\d+)', data)
                require(statuses and int(statuses[-1]) == expected, 'unexpected exit for '+line+': '+repr(data[-2000:]))
                require(resources(guest) == baseline, 'resource drift after '+line)
                return data
            for row, (name, _, good) in zip(report['cases'], cases):
                command('xypm verify /out/'+name+'.xpk', 0 if good else 3)
                row['guest'] = good
            command('xypm plan install /out/valid.xpk', 0)
            report['checks'].append('empty_database_install_plan')
            command('xypm plan upgrade /out/valid.xpk', 3)
            report['checks'].append('missing_upgrade_rejected')
            command('xypm verify /out/valid.xpk ' + '0'*64, 3)
            report['checks'].append('expected_package_hash_mismatch')
            guest.close(); (out/'first_serial.log').write_bytes(guest.output); guest = None
            installed = folder/'installed.img'
            transact(disk, installed, profile, 'install', package=folder/'valid.xpk')
            require(query_image(installed, profile, 'verify-installed')['files'] == 3, 'host installed files differ')
            for name, path in plan_cases:
                try:
                    transact(installed, folder/(name+'.img'), profile, 'install', package=path)
                    host_ok = True
                except PackageError:
                    host_ok = False
                require(host_ok == (name == 'dep_good'), 'host plan expectation differs: '+name)
                report['cases'].append({'name': name, 'sha256': sha_file(path), 'host': host_ok})
            guest = Guest(boot, 'package_p2_installed', work_disk=installed)
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest)
            command('xypm plan upgrade /out/valid.xpk', 0)
            command('xypm plan install /out/valid.xpk', 3)
            command('xypm plan remove friends.p2', 0)
            command('xypm plan remove friends.missing', 3)
            report['checks'].append('installed_database_upgrade_and_duplicate_install')
            report['checks'].append('installed_and_missing_remove_plan')
            for name, _ in plan_cases:
                command('xypm plan install /out/'+name+'.xpk', 0 if name == 'dep_good' else 3)
                next(row for row in report['cases'] if row['name'] == name)['guest'] = name == 'dep_good'
                report['checks'].append('plan_'+name)
            if args.dash_elf:
                command('dash /tests/dash_check.sh', 0)
                report['checks'].append('dash_verify_plan_and_error_status')
                start = len(guest.output); send_bytes(guest, b'dash -i\r'); guest.expect(b'$ ', start=start, timeout=60)
                start = len(guest.output); send_bytes(guest, b'xypm install /out/valid.xpk; echo DASH_STATUS=$?\r')
                guest.expect(b'DASH_STATUS=3', start=start, timeout=60); guest.expect(b'$ ', start=start, timeout=60)
                require(b'maintenance write lease required' in bytes(guest.output)[start:], 'dash unexpectedly gained write lease')
                start = len(guest.output); send_bytes(guest, b'exit\r'); guest.expect_supervisor(start=start, timeout=60)
                start = len(guest.output); send_bytes(guest, b'maint-run /usr/bin/xypm upgrade /out/valid.xpk\r')
                guest.expect(b'maintenance: completed', start=start, timeout=300); guest.expect_supervisor(start=start, timeout=60)
                report['checks'].append('dash_exit_then_maintenance_upgrade')
            guest.close(); (out/'installed_serial.log').write_bytes(guest.output); guest = None
            if args.dash_elf:
                with Disk(installed, folder, True) as backend:
                    require(b'Package verified: friends.p2' in backend.export('/out/dash_ok.txt').read_bytes(), 'dash redirected stdout missing')
                    require(b'payload hash mismatch' in backend.export('/out/dash_error.txt').read_bytes(), 'dash redirected stderr missing')
                report['checks'].append('dash_redirected_results')
            guest = Guest(boot, 'package_p2_reverse_dependency', work_disk=folder/'dep_good.img')
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest)
            command('xypm plan remove friends.p2', 3)
            command('xypm plan remove friends.dependent', 0)
            report['checks'].append('remove_plan_checks_reverse_dependencies')
            guest.close(); (out/'reverse_dependency_serial.log').write_bytes(guest.output); guest = None
            cycle_disk = folder/'dep_good.img'
            with Disk(cycle_disk, folder) as backend:
                database = json.loads(backend.export('/var/lib/xypm/db.json').read_text())
                dependent_record = database['packages']['friends.dependent']
                database['packages']['friends.p2']['manifest']['runtime_dependencies'] = [{
                    'id': 'friends.dependent', 'upstream_version': '1.0', 'revision': 2147483647,
                    'sha256': dependent_record['sha256']}]
                cycle = folder/'cycle_db.json'; cycle.write_bytes(canonical(database))
                backend.command('remove', '/var/lib/xypm/db.json')
                backend.command('import', '/var/lib/xypm/db.json', cycle)
            try:
                with Disk(cycle_disk, folder, True) as backend:
                    validate_dependencies(load_db(backend, profile))
                raise AssertionError('host accepted dependency cycle')
            except PackageError:
                pass
            guest = Guest(boot, 'package_p2_cycle', work_disk=cycle_disk)
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest)
            command('xypm plan remove friends.dependent', 3)
            report['checks'].append('host_and_guest_reject_database_dependency_cycle')
            guest.close(); (out/'cycle_serial.log').write_bytes(guest.output); guest = None
            with Disk(installed, folder) as backend:
                original_data = backend.export('/usr/share/p2/data.txt').read_bytes()
                backend.command('remove', '/usr/share/p2/data.txt')
                modified = folder/'modified'; modified.write_bytes(b'X'+original_data[1:])
                backend.command('import', '/usr/share/p2/data.txt', modified)
            try:
                query_image(installed, profile, 'verify-installed')
                raise AssertionError('host accepted modified managed file')
            except PackageError:
                pass
            guest = Guest(boot, 'package_p2_modified', work_disk=installed)
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest)
            command('xypm plan upgrade /out/valid.xpk', 3)
            report['checks'].append('host_and_guest_reject_modified_managed_file')
            guest.close(); (out/'modified_serial.log').write_bytes(guest.output); guest = None
            with Disk(installed, folder) as backend:
                backend.command('remove', '/usr/share/p2/data.txt')
                original = folder/'original'; original.write_bytes(original_data)
                backend.command('import', '/usr/share/p2/data.txt', original)
                backend.command('remove', '/var/lib/xypm/index.tsv')
                broken = folder/'broken_index'; broken.write_bytes(b'xypm-index-v1\ncorrupt\n')
                backend.command('import', '/var/lib/xypm/index.tsv', broken)
            try:
                query_image(installed, profile, 'verify-installed')
                raise AssertionError('host accepted corrupt index')
            except PackageError:
                pass
            guest = Guest(boot, 'package_p2_corrupt_db', work_disk=installed)
            guest.expect(b'xos64> ', timeout=40); send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=40); pump(guest, 1.5)
            baseline = resources(guest)
            command('xypm plan upgrade /out/valid.xpk', 3)
            report['checks'].append('host_and_guest_reject_corrupt_index')
            report['status'] = 'passed'
    except Exception as exc:
        report['error'] = str(exc)
        if guest: report['output_tail'] = bytes(guest.output[-6000:]).decode(errors='replace')
        raise
    finally:
        if guest:
            guest.close(); (out/'serial.log').write_bytes(guest.output)
        (out/'verify_report.json').write_bytes(canonical(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
