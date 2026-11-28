# SPDX-License-Identifier: Apache-2.0
"""Fetch from real GHCR inside XOS, then install on the same disposable FAT disk."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import tempfile

from native_tls_guest import Guest, boot, command, create_fat32, sha, start_network, transfer

DIGEST = re.compile(r'[a-f0-9]{64}')
REPO = re.compile(r'[a-z0-9][a-z0-9._/-]{1,254}')
PACKAGE = re.compile(r'[a-z][a-z0-9._-]{0,79}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('system', 'trust', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--trust-generation', required=True, type=int)
    parser.add_argument('--trust-sha256', required=True)
    parser.add_argument('--registry-ip', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--blob-ip', required=True, type=ipaddress.IPv4Address)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--xypm', type=Path)
    parser.add_argument('--fetcher', type=Path)
    parser.add_argument('--package-id', help='omit only to probe real GHCR through manifest validation')
    parser.add_argument('--package-sha256', help='expected XPK digest for the installation run')
    parser.add_argument('--download-sha256', help='verify the exported package without installing')
    args = parser.parse_args()
    if (not REPO.fullmatch(args.repository) or args.trust_generation <= 0
            or not DIGEST.fullmatch(args.trust_sha256)
            or not DIGEST.fullmatch(args.manifest_sha256)
            or (args.package_sha256 and (not args.package_id or not DIGEST.fullmatch(args.package_sha256)))
            or (args.download_sha256 and (args.package_id or not DIGEST.fullmatch(args.download_sha256)))
            or (args.package_id and (not args.xypm or not PACKAGE.fullmatch(args.package_id)))):
        parser.error('invalid registry, digest, generation, or package id')
    if not args.package_id and not args.fetcher:
        parser.error('--fetcher is required for probe or download-only mode')
    if sha(args.trust) != args.trust_sha256:
        parser.error('trust snapshot differs from the independently supplied pin')
    args.output.mkdir(parents=True, exist_ok=False)
    image = args.system / 'xos-install.iso'
    report = {'status': 'failed', 'repository': args.repository,
              'manifest_sha256': args.manifest_sha256, 'ca_sha256': args.trust_sha256,
              'image_sha256': sha(image), 'fetcher_sha256': sha(args.fetcher) if args.fetcher else None,
              'xypm_sha256': sha(args.xypm) if args.xypm else None, 'expected_package_id': args.package_id}
    try:
        with tempfile.TemporaryDirectory(prefix='xos-ghcr-') as folder:
            disk = Path(folder) / 'work.img'
            create_fat32(disk, 512)
            for path in ('/bin', '/usr', '/usr/bin'):
                transfer(disk, 'mkdir', path)
            fetch_command = 'exec-file /bin/f.elf'
            if args.package_id:
                transfer(disk, 'import', '/usr/bin/xypm', args.xypm)
                fetch_command = 'exec-file /usr/bin/xypm ghcr-fetch'
            else:
                transfer(disk, 'import', '/bin/f.elf', args.fetcher)
            transfer(disk, 'import', '/ca.bin', args.trust)
            guest = Guest(image, 'ghcr', iso=True, work_disk=disk, network=True,
                          qmp_enabled=False, log_dir=args.output)
            try:
                boot(guest)
                active = re.findall(rb"\[net-start\] pid=(\d+)", bytes(guest.output))
                if active:
                    guest.expect(b"[net] ready native_v2=1", start=0)
                    pid = int(active[-1])
                else:
                    pid = start_network(guest)
                invocation = (f'{fetch_command} {pid} {args.registry_ip} {args.blob_ip} /ca.bin '
                              f'{args.trust_generation} {args.trust_sha256} {args.repository} '
                              f'sha256:{args.manifest_sha256} /fetch')
                result = command(guest, invocation, b'kind=exited code=', timeout=625)
                report['download'] = result.decode(errors='replace')
                if not args.package_id and not args.download_sha256:
                    if b'XYP_GHCR_TOKEN_OK' not in result or b'xypm-ghcr: OCI manifest is not an XPK artifact (0)' not in result:
                        raise AssertionError('live token and pinned non-XPK manifest were not verified')
                    report['status'] = 'public_non_xpk_manifest_rejected'
                    return
                matched = re.search(rb'XYP_GHCR_VERIFIED path=/fetch/package.xpk sha256=([0-9a-f]{64})', result)
                if not matched or b'kind=exited code=0' not in result:
                    raise AssertionError('native GHCR XPK download/verification failed')
                digest = matched[1].decode()
                report['downloaded_xpk_sha256'] = digest
                if args.package_sha256 and digest != args.package_sha256:
                    raise AssertionError('downloaded XPK differs from the expected published package')
                if args.download_sha256:
                    if digest != args.download_sha256:
                        raise AssertionError('verified layer differs from expected XPK')
                    guest.close()
                    guest = None
                    delivered = args.output / 'package.xpk'
                    transfer(disk, 'export', '/fetch/package.xpk', delivered)
                    if sha(delivered) != digest:
                        raise AssertionError('exported XPK differs from verified layer')
                    report['status'] = 'downloaded_verified'
                    return
                command(guest, 'net-stop', b'xsh>')
                command(guest, 'audio stop', b'xsh>')
                installed = command(guest, f'maint-run /usr/bin/xypm install /fetch/package.xpk --sha256 {digest}',
                                    b'xsh>', timeout=120)
                report['install'] = installed.decode(errors='replace')
                if b'maintenance: completed' not in installed:
                    raise AssertionError('native xypm installation failed')
                queried = command(guest, f'exec-file /usr/bin/xypm info {args.package_id}', b'kind=exited code=')
                report['installed_identity'] = queried.decode(errors='replace')
                if (f'id: {args.package_id}'.encode() not in queried
                        or f'sha256: {digest}'.encode() not in queried or b'kind=exited code=0' not in queried):
                    raise AssertionError('installed package identity differs')
                guest.close()
                guest = None
                database = args.output / 'db.json'
                transfer(disk, 'export', '/var/lib/xypm/db.json', database)
                state = json.loads(database.read_bytes())
                record = state['packages'][args.package_id]
                if record['sha256'] != digest or record['manifest']['id'] != args.package_id:
                    raise AssertionError('persisted database identity differs from installed package')
                report['database_sha256'] = sha(database)
                report['installed_profile'] = record['manifest']['target_profile']
                report['status'] = 'passed'
            finally:
                if guest:
                    guest.close()
    finally:
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
