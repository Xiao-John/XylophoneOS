# SPDX-License-Identifier: Apache-2.0
"""Check the explicit static glibc dash preview through xsh and legacy dash."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from install_dash import install
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, bind_tool, check_hash, relative_file, sha
from task_smoke import send_bytes
from work_disk import transfer
from xypm_format import load_json
from xypm_sdk_profile import verify_profile

BUILTINS = r'''value=xos
test "$value" = xos || exit 41
test "$1" = alpha || exit 43
probe() { printf '%s\n' "$1"; }
case "$value" in
    xos) probe "${fallback:-DASH_GLIBC_BUILTINS_PASS}" ;;
    *) exit 42 ;;
esac
'''
FILES = r'''printf '%s\n' 'glibc dash file bytes' > /out/files.txt || exit 51
read value < /out/files.txt || exit 52
test "$value" = 'glibc dash file bytes' || exit 53
. /cases/dot.inc || exit 54
printf '%s\n' "$source_marker"
'''
CASES = {
    'builtins': (BUILTINS, 0, b'DASH_GLIBC_BUILTINS_PASS', ' alpha'),
    'files': (FILES, 0, b'DASH_GLIBC_FILES_PASS', ''),
    'pipeline': ("printf unexpected | printf unexpected\n", 2, b'pipelines unavailable', ''),
    'subshell': ("(printf unexpected)\n", 2, b'subshells unavailable', ''),
    'substitution': ('printf "%s\\n" "$(printf unexpected)"\n', 2, b'command substitution unavailable', ''),
    'heredoc': ("read value <<EOF\nunexpected\nEOF\n", 2, b'here-documents unavailable', ''),
    'external': ("/bin/dash_glibc /cases/builtins.sh alpha\n", 126, b'external commands unavailable', ''),
}


def bind_preview(args):
    receipt = load_json(args.preview_receipt)
    if receipt.get('profile') != 'dash_glibc_preview' or receipt.get('status') != 'built_not_run':
        raise ValueError('expected a glibc dash preview build receipt')
    sdk = args.glibc_sdk / 'sysroot'
    binding = verify_profile(load_json(args.glibc_profile), 'glibc', args.glibc_sdk)
    if binding != receipt.get('sdk_profile_binding') or binding['profile_sha256'] != receipt['inputs']['profile']:
        raise ValueError('dash build must bind the supplied glibc profile')
    check_hash(args.glibc_sdk / 'manifest.json', receipt['sdk_manifest_sha256'], 'glibc dash SDK')
    sdk_files = {'sdk/' + path.relative_to(sdk).as_posix() for path in sdk.rglob('*') if path.is_file()}
    sdk_files.add('sdk/manifest.json')
    if sdk_files != {name for name in receipt['inputs'] if name.startswith('sdk/')}:
        raise ValueError('dash receipt must bind the complete glibc SDK')
    for name, digest in receipt['inputs'].items():
        if name == 'profile':
            continue
        source = (args.glibc_sdk / 'manifest.json' if name == 'sdk/manifest.json' else
                  relative_file(sdk, name[4:]) if name.startswith('sdk/') else relative_file(ROOT, name))
        check_hash(source, digest, 'glibc dash input')
    path = relative_file(ROOT, receipt['elf'])
    if path.relative_to(ROOT).parts[:3] != ('.cache', 'xos_seed', 'dash_glibc_preview'):
        raise ValueError('glibc dash must use its separate preview cache')
    check_hash(path, receipt['sha256'], 'glibc dash ELF')
    return {'receipt_sha256': sha(args.preview_receipt), 'elf_sha256': receipt['sha256'],
            'sdk_manifest_sha256': receipt['sdk_manifest_sha256'], 'profile': binding}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ('system', 'legacy-receipt', 'preview-receipt', 'glibc-sdk', 'glibc-profile', 'artifacts'):
        parser.add_argument('--' + argument, type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=False)
    report = {'status': 'failed', 'runner_sha256': sha(Path(__file__)), 'runs': [], 'fixtures': {}}
    guest = None
    try:
        system = bind_system(args.system)
        iso = args.system / 'xos-install.iso'
        _, legacy = bind_tool(args.legacy_receipt, 'dash_c3', args.system / 'sdk')
        report.update(system_build_id=system['build_id'], iso_sha256=sha(iso),
                      system_manifest_sha256=sha(args.system / 'manifest.json'),
                      legacy=legacy, preview=bind_preview(args))
        with tempfile.TemporaryDirectory(prefix='xos_dash_glibc_') as folder:
            work = Path(folder)
            disk = work / 'work.img'
            create_fat32(disk, 512)
            install(disk, args.legacy_receipt)
            install(disk, args.preview_receipt, '/bin/dash_glibc')
            for path in ('/cases', '/out'):
                transfer(disk, 'mkdir', path)
            fixtures = {'dot.inc': 'source_marker=DASH_GLIBC_FILES_PASS\n'}
            for name, (source, _, _, arguments) in CASES.items():
                fixtures[name + '.sh'] = source
                fixtures['via_dash_' + name + '.sh'] = (
                    f'/bin/dash_glibc /cases/{name}.sh{arguments}\nstatus=$?\n'
                    'printf "DASH_GLIBC_EXIT=%s\\n" "$status"\nexit "$status"\n')
            for name, source in fixtures.items():
                path = args.artifacts / name
                path.write_text(source)
                report['fixtures'][name] = sha(path)
                transfer(disk, 'import', '/cases/' + name, path)
            guest = Guest(iso, 'dash_glibc_preview', work_disk=disk, iso=True, qmp_enabled=False)
            report['qemu'] = subprocess.check_output([guest.command[0], '--version'], text=True).splitlines()[0]
            guest.expect(b'xos64> ', timeout=60)
            send_bytes(guest, b'run\r')
            guest.expect_supervisor(trace=True, timeout=60)
            command(guest, 'demo quiet', b'demo tasks')
            baseline = resources(guest)
            report['baseline'] = baseline
            for shell in ('xsh', 'dash'):
                for name, (_, status, marker, arguments) in CASES.items():
                    line = (f'exec-file /bin/dash_glibc /cases/{name}.sh{arguments}' if shell == 'xsh'
                            else f'dash /cases/via_dash_{name}.sh')
                    capture = command(guest, line, b'[wait] pid=', timeout=40)
                    record = {'case': name, 'shell': shell, 'output': capture.decode(errors='replace')}
                    report['runs'].append(record)
                    waited = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', capture)
                    expected = str(status).encode()
                    assert waited == [(b'exited', expected)] and marker in capture, capture
                    if shell == 'dash':
                        assert b'DASH_GLIBC_EXIT=' + expected + b'\n' in capture, capture
                    if status:
                        assert b'unexpected' not in capture and b'DASH_GLIBC_BUILTINS_PASS' not in capture, capture
                    after = resources(guest)
                    assert after == baseline, (baseline, after)
                    record.update(exit_code=status, resources=after)
            command(guest, 'sync', b'[files] sync=ok')
            guest.close()
            exported = args.artifacts / 'files.txt'
            transfer(disk, 'export', '/out/files.txt', exported)
            assert exported.read_bytes() == b'glibc dash file bytes\n'
            report.update(status='passed_subset', file_sha256=sha(exported))
    finally:
        if guest:
            guest.close()
            log = args.artifacts / 'serial.log'
            log.write_bytes(guest.output)
            report['serial_sha256'] = sha(log)
        (args.artifacts / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
