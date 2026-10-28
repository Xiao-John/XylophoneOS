# SPDX-License-Identifier: Apache-2.0
"""Offline XPK install, guest use and removal on private FAT images."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer


def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--dash', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    report = {'status':'failed', 'image_sha256':hashlib.sha256(a.image.read_bytes()).hexdigest(),
              'package_sha256':hashlib.sha256(a.package.read_bytes()).hexdigest(),
              'profile_sha256':hashlib.sha256(a.profile.read_bytes()).hexdigest(),
              'dash_sha256':hashlib.sha256(a.dash.read_bytes()).hexdigest(), 'checks':[]}
    def xypm(*args):
        p = subprocess.run([sys.executable, str(ROOT/'scripts/xypm.py'), *map(str,args),
                            '--profile', str(a.profile)], text=True, capture_output=True)
        if p.returncode: raise RuntimeError('xypm failed: ' + p.stderr)
        return json.loads(p.stdout)
    try:
        with tempfile.TemporaryDirectory(prefix='xos_du_package_') as tmp:
            root=Path(tmp); empty=root/'empty.img'; installed=root/'installed.img'; removed=root/'removed.img'
            create_fat32(empty, 512)
            bad = root/'bad.xpk'; corrupted = bytearray(a.package.read_bytes()); corrupted[0] ^= 1; bad.write_bytes(corrupted)
            check = subprocess.run([sys.executable, str(ROOT/'scripts/xypm.py'), 'verify', str(bad),
                                    '--profile', str(a.profile)], capture_output=True)
            assert check.returncode != 0
            report['checks'].append('corrupt_package_rejected')
            conflict = root/'conflict.img'; rejected = root/'rejected.img'; create_fat32(conflict, 512)
            for path in ('/usr','/usr/bin'): transfer(conflict, 'mkdir', path)
            user_file = root/'existing'; user_file.write_bytes(b'user-owned-file')
            transfer(conflict, 'import', '/usr/bin/ls', user_file)
            before = sha_file(conflict)
            result = subprocess.run([sys.executable, str(ROOT/'scripts/xypm.py'), 'install', str(a.package),
                                     '--image', str(conflict), '--output-image', str(rejected), '--offline',
                                     '--profile', str(a.profile)], capture_output=True)
            assert result.returncode != 0 and not rejected.exists()
            assert sha_file(conflict) == before
            report['checks'].append('unmanaged_conflict_preserves_source_image')
            install=xypm('install',a.package,'--image',empty,'--output-image',installed,'--offline')
            assert install['id']=='xos.daily_utilities' and install['verified_files']==27
            report['checks'].append('offline_install_verified_payload')
            for d in ('/tmp','/tests'): transfer(installed,'mkdir',d)
            transfer(installed,'import','/usr/bin/dash',a.dash)
            transfer(installed,'import','/tests/du12.sh',ROOT/'tests/fixtures/daily_utilities/du12.sh')
            transfer(installed,'import','/tests/binary.dat',ROOT/'tests/fixtures/daily_utilities/binary.dat')
            guest=Guest(a.image,'daily_package',work_disk=installed)
            try:
                guest.expect(b'xos64> ',timeout=30);start=len(guest.output);send_bytes(guest,b'run\r')
                guest.expect_supervisor(start=start,timeout=40);pump(guest,.4)
                send_bytes(guest,b'demo quiet\r');pump(guest,.4)
                start=len(guest.output);send_bytes(guest,b'dash /tests/du12.sh\r')
                guest.expect_supervisor(start=start,timeout=180); output=bytes(guest.output[start:])
                if b'DU12_OK' not in output: raise AssertionError(output[-4000:].decode('utf-8','replace'))
                start=len(guest.output);send_bytes(guest,b'sync\r');guest.expect_supervisor(start=start,timeout=30)
            finally:guest.close()
            report['checks'].append('installed_tools_guest_dash_pipe')
            data=root/'result';transfer(installed,'export','/tmp/du/tail_pipe.txt',data)
            assert data.read_bytes()==b'b\nc'
            verify=xypm('verify-installed','--image',installed)
            assert verify['status']=='verified' and verify['files']==27
            report['checks'].append('sync_result_and_installed_hashes')
            result=xypm('remove','xos.daily_utilities','--image',installed,'--output-image',removed,'--offline')
            assert result['id']=='xos.daily_utilities'
            assert xypm('list','--image',removed)['packages']==[]
            saved=root/'saved';transfer(removed,'export','/tmp/du/tail_pipe.txt',saved)
            assert saved.read_bytes()==b'b\nc'
            report['checks'].append('remove_preserves_user_file')
        report['status']='passed'
    finally:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
