# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
from pathlib import Path
import re
from subprocess import check_output, run
from types import SimpleNamespace

from boot_smoke import Guest
from dash_glibc_preview_guest import bind_preview
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system
from task_smoke import send_bytes
from work_disk import transfer
from xypm_sdk_profile import verify_profile

root = Path.cwd()
parser = argparse.ArgumentParser()
for name in ('kit', 'system', 'dash_receipt', 'output'):
    parser.add_argument(name, type=lambda value: Path(value).resolve())
args = parser.parse_args()
args.output.mkdir()

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

profile = args.kit / 'profile.json'
sdk = args.kit / 'sdk'
image = args.system / 'xos-install.iso'
binding = verify_profile(json.loads(profile.read_bytes()), 'glibc', sdk)
system = bind_system(args.system)
dash = bind_preview(SimpleNamespace(preview_receipt=args.dash_receipt, glibc_sdk=sdk, glibc_profile=profile))
dash_elf = root / json.loads(args.dash_receipt.read_bytes())['elf']
report = {'status': 'failed', 'system_build_id': system['build_id'], 'iso_sha256': sha(image),
          'system_manifest_sha256': sha(args.system / 'manifest.json'), 'sdk_manifest_sha256': sha(sdk / 'manifest.json'),
          'binding': binding, 'dash': dash, 'runner_sha256': sha(__file__), 'elfs': {}, 'checks': []}
programs = {
    'thread': ('xypm/glibc_profile_program.cpp', b'xypm external glibc C++'),
    'exception': ('cpp_abi/exception_probe.cpp', b'[cpp_abi] exception_unwind=ok'),
}
shell = args.output / 'apps.sh'
shell.write_text('set -e\n/bin/thread\n/bin/exception\n'
                 'value=$(printf "%s" current-sdk)\n'
                 'test "$value" = current-sdk\n'
                 'printf "GLIBC_CXX_FORK_KIT_OK\\n"\n')
report['dash_fixture_sha256'] = sha(shell)
guest = None
try:
    disk = args.output / 'work.img'
    create_fat32(disk, 512)
    transfer(disk, 'mkdir', '/bin')
    transfer(disk, 'import', '/bin/dash_glibc', dash_elf)
    transfer(disk, 'import', '/bin/apps.sh', shell)
    for name, (source, _) in programs.items():
        fixture = root / 'tests/fixtures' / source
        elf = args.output / f'{name}.elf'
        run(['python3', 'scripts/build_glibc_program.py', '--sdk', sdk / 'sysroot', '--profile', profile,
             '--cxx', '--stdio-transfer', '--source', fixture, '--output', elf], check=True)
        build = elf.with_suffix('.elf.build') / 'manifest.json'
        receipt = json.loads(build.read_bytes())
        assert receipt['status'] == 'static_program_linked' and receipt['language'] == 'c++'
        assert receipt['profile_binding'] == binding
        assert receipt['elf_sha256'] == sha(elf) and receipt['sources'] == {str(fixture): sha(fixture)}
        transfer(disk, 'import', '/bin/' + name, elf)
        readback = args.output / (name + '.fat')
        transfer(disk, 'export', '/bin/' + name, readback)
        assert sha(readback) == sha(elf), name
        report['elfs'][name] = {'sha256': sha(elf), 'source_sha256': sha(fixture), 'source': source,
                                'build_receipt_sha256': sha(build), 'fat_readback_sha256': sha(readback)}
    guest = Guest(image, 'glibc_cxx_current_kit', work_disk=disk, iso=True, qmp_enabled=False, log_dir=args.output)
    report['qemu'] = check_output([guest.command[0], '--version'], text=True).splitlines()[0]
    guest.expect(b'xos64> ', timeout=60)
    send_bytes(guest, b'run\r')
    guest.expect_supervisor(trace=True, timeout=60)
    command(guest, 'demo quiet', b'demo tasks')
    baseline = resources(guest)
    report['baseline'] = baseline
    cases = [('xsh', f'exec-file /bin/{name}', (marker,)) for name, (_, marker) in programs.items()]
    cases.append(('glibc-dash', '/bin/dash_glibc /bin/apps.sh',
                  tuple(marker for _, marker in programs.values()) + (b'GLIBC_CXX_FORK_KIT_OK',)))
    for _ in range(3):
        for caller, line, markers in cases:
            capture = command(guest, line, b'[wait] pid=', timeout=120)
            exits = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', capture)
            after = resources(guest)
            assert exits == [(b'exited', b'0')] and all(marker in capture for marker in markers), capture
            assert after == baseline, (caller, after, baseline)
            report['checks'].append({'shell': caller, 'command': line, 'markers': [m.decode() for m in markers],
                                     'resources': after, 'exit_code': 0})
    assert report['iso_sha256'] == sha(image)
    assert verify_profile(json.loads(profile.read_bytes()), 'glibc', sdk) == binding
    assert dash['elf_sha256'] == sha(dash_elf)
    report['status'] = 'passed_subset'
finally:
    if guest is not None:
        guest.close()
        serial = args.output / 'guest.serial.log'
        serial.write_bytes(bytes(guest.output))
        report['serial_sha256'] = sha(serial)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
print(report['status'])
