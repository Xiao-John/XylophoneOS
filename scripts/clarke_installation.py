#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bind the three fixed ClarkE programs to an actual verified bundle manifest."""
from hashlib import file_digest
import json
from pathlib import Path
from build_glibc_program import verify_elf

DESTINATIONS = {'viewport.elf': '/usr/bin/clarke.elf',
                'network.elf': '/usr/libexec/clarke/network.elf',
                'renderer.elf': '/usr/libexec/clarke/renderer.elf'}
LIMITS = {'viewport.elf': (1,32768,4,16,0,4), 'network.elf': (1,16384,2,16,0,4),
          'renderer.elf': (1,65536,4,16,0,4)}


def digest(path):
    with path.open('rb') as stream: return file_digest(stream, 'sha256').hexdigest()


def bind(bundle, output):
    bundle = Path(bundle).resolve(strict=True)
    report_path = bundle / 'manifest.json'
    if report_path.is_symlink(): raise ValueError('ClarkE manifest must be a regular file')
    report_hash = digest(report_path)
    report = json.loads(report_path.read_bytes())
    if report.get('status') != 'clarke_webcore_browser_linked':
        raise ValueError('ClarkE installation requires a fully linked WebCore/Qt bundle')
    entries = []; files = {}
    for name, destination in DESTINATIONS.items():
        path = bundle / name
        if path.is_symlink() or not path.is_file() or not 64 <= path.stat().st_size < 2**32:
            raise ValueError('select a regular bounded ClarkE ELF: ' + name)
        expected = report['artifacts'][name]
        if digest(path) != expected: raise ValueError('ClarkE ELF differs from bundle receipt: ' + name)
        headers = verify_elf(path)
        pages = sum(((item['virtual_address'] + item['memory_size'] + 4095) // 4096 - item['virtual_address'] // 4096)
                    for item in headers if item['type'] == 1)
        if pages + 256 > LIMITS[name][1]: raise ValueError('ClarkE ELF exceeds role page budget: ' + name)
        encoded = ','.join('0x' + expected[index:index+2] for index in range(0,64,2))
        entries.append('{"' + destination + '",{{' + encoded + '},' + str(path.stat().st_size) + '},{' +
                       ','.join(map(str,LIMITS[name])) + '}}')
        files[destination] = {'artifact': name, 'sha256': expected, 'bytes': path.stat().st_size, 'limits': LIMITS[name]}
    font = bundle / 'DejaVuSans.ttf'
    if font.is_symlink() or digest(font) != report['artifacts']['DejaVuSans.ttf']:
        raise ValueError('ClarkE font differs from the bundle')
    files['/usr/share/fonts/clarke/DejaVuSans.ttf'] = {'artifact': font.name, 'sha256': digest(font), 'bytes': font.stat().st_size}
    if digest(report_path) != report_hash: raise ValueError('ClarkE manifest changed during binding')
    Path(output).write_text('// SPDX-License-Identifier: Apache-2.0\n#pragma once\n'
        'inline constexpr xos::clarke::installation clarke_installed{' + ',\n'.join(entries) + '};\n')
    return {'clarke': {'bundle_manifest_sha256': report_hash, 'sdk_manifest_sha256': report['sdk_manifest_sha256'],
                       'sdk_profile_sha256': report['sdk_profile_sha256'], 'files': files,
                       'network_policy': report['network_policy'], 'test_profile': report.get('test_profile')}}


def bind_probe(source, output):
    source = Path(source)
    if source.is_symlink() or not source.is_file() or not 64 <= source.stat().st_size <= 1024 * 1024:
        raise ValueError('select a regular small launch probe ELF')
    headers = verify_elf(source)
    pages = sum((item['memory_size'] + 8190) // 4096 for item in headers if item['type'] == 1)
    if pages + 64 > 1024: raise ValueError('probe image exceeds isolated page budget')
    receipt = digest(source)
    encoded = ','.join('0x' + receipt[index:index+2] for index in range(0,64,2))
    Path(output).write_text('// SPDX-License-Identifier: Apache-2.0\n#pragma once\n'
        'inline constexpr xos::execution::image_receipt clarke_launch_receipt{{' + encoded + '},' + str(source.stat().st_size) + '};\n')
    return {'clarke_launch_probe': {'path':'/clarke_launch.elf','sha256':receipt,'bytes':source.stat().st_size,
                                   'loader_flag':'XOS_LOADER_TEST_BAD_START_ENTRY=1'}}
