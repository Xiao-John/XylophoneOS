# SPDX-License-Identifier: Apache-2.0
"""Check the explicit static glibc dash preview through xsh and legacy dash."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from boot_smoke import Guest
from dash_c3_smoke import reserved_snapshot
from install_dash import install
from make_work_disk import create_fat32
from process_smoke import command, resources
from shell_launch_support import bind_system, bind_tool, check_hash, relative_file, sha
from task_smoke import send_bytes
from toolchain import COMMON_FLAGS, X86_FLAGS, tool
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
HEREDOC = r'''word=expanded
IFS= read -r literal <<'QUOTED' || exit 65
literal $word \keep
QUOTED
test "$literal" = 'literal $word \keep' || exit 66
IFS= read -r expanded <<UNQUOTED || exit 67
expanded:$word:$((7+5))
UNQUOTED
test "$expanded" = 'expanded:expanded:12' || exit 68
word=outer
word=inner IFS= read -r prefixed <<ASSIGNMENT || exit 72
$word
ASSIGNMENT
test "$prefixed:$word" = 'outer:outer' || exit 73
printf 'DASH_GLIBC_HERE_PASS <%s> <%s>\n' "$literal" "$expanded"
'''
HEREDOC_FAILURE = r'''i=0
while [ "$i" -lt 24 ]; do
    if IFS= read -r unused <<DISCARDED >/missing/heredoc-output; then
discarded line $i
DISCARDED
        exit 69
    fi
    i=$((i+1))
done
IFS= read -r recovered <<RECOVERED || exit 70
recovered document
RECOVERED
test "$recovered" = 'recovered document' || exit 71
printf 'DASH_GLIBC_HERE_RECOVERED=%s\n' "$i"
'''
EXTERNAL = r'''cd /cases || exit 61
PATH=/missing:/bin
export PATH
DASH_GLIBC_TOKEN='ordinary value' {command}
status=$?
printf 'DASH_GLIBC_CHILD_RC=%s\n' "$status"
exit "$status"
'''
EXPLICIT = EXTERNAL.format(command="/bin/preview_child explicit 'two words' ''")
PIPELINE = r'''PATH=/missing:/bin
export PATH
/bin/stream_child emit | stream_child relay | /bin/stream_child verify || exit 81
printf 'DASH_GLIBC_PIPE_PASS\n'
'''
PIPE_STATUS = r'''set -o pipefail
/bin/stream_child emit7 | /bin/stream_child verify
test "$?" -eq 7 || exit 82
/bin/stream_child emit-close | /bin/stream_child one || exit 83
printf 'DASH_GLIBC_PIPE_STATUS_PASS\n'
'''
PIPE_REDIRECT = r'''/bin/stream_child emit | /bin/stream_child relay >/out/pipeline.bin || exit 84
/bin/stream_child verify </out/pipeline.bin || exit 85
printf 'DASH_GLIBC_PIPE_FILE_PASS\n'
'''
PIPE_CLOSED = r'''exec 0<&- 2>&-
/bin/stream_child emit | /bin/stream_child verify || exit 86
/bin/stream_child closed-err || exit 87
printf 'DASH_GLIBC_PIPE_CLOSED_PASS\n'
'''
PIPE_FAILURE = r'''i=0
while [ "$i" -lt 8 ]; do
    /bin/stream_child emit | /bin/not_present
    test "$?" -eq 127 || exit 81
    i=$((i+1))
done
/bin/stream_child emit | /bin/stream_child verify || exit 82
printf 'DASH_GLIBC_PIPE_RECOVERED=%s\n' "$i"
'''
SUBSTITUTION = r'''set -- 'two words' ''
value=parent
probe() { printf '%s:%s\n\n' "$value" "$1"; }
result=$(probe "$1")
test "$result" = 'parent:two words' || exit 101
legacy=`printf '%s\n\n' backticks`
test "$legacy" = backticks || exit 102
result=$(value=child; cd /cases && probe "$1"; printf '%s\n\n' "$PWD")
test "$result" = 'child:two words

/cases' || exit 103
test "$value:$PWD:$#" = 'parent:/:2' || exit 104
result=$(printf '%s' "$(printf nested)")
test "$result" = nested || exit 105
result=$(printf 'nonzero\n'; exit 23)
test "$?:$result" = '23:nonzero' || exit 106
result=$(false)
test "$?:$result" = '1:' || exit 107
printf 'DASH_GLIBC_SUBSTITUTION_PASS\n'
'''
SUBSTITUTION_STREAM = r'''result=$(printf '%10037s' '')
test "${#result}" -eq 10037 || exit 101
printf '%s\n' 'file input' >/out/substitution.in || exit 102
result=$(/bin/stream_child line </out/substitution.in) || exit 103
test "$result" = 'file input' || exit 104
result=$(/bin/stream_child emit | /bin/stream_child verify) || exit 105
test "$result" = DASH_GLIBC_STREAM_BYTES=10037 || exit 106
set -o pipefail
result=$(/bin/stream_child emit7 | /bin/stream_child verify)
test "$?:$result" = '7:DASH_GLIBC_STREAM_BYTES=10037' || exit 107
printf 'DASH_GLIBC_SUBSTITUTION_STREAM_PASS\n'
'''
SUBSTITUTION_CLOSE = r'''exec 0<&- 2>&-
result=$(printf retained)
test "$result" = retained || exit 101
/bin/stream_child closed-err || exit 102
printf 'DASH_GLIBC_SUBSTITUTION_CLOSE_PASS\n'
'''
REDIRECT = r'''printf '%s\n' 'file input' >/out/stream.in || exit 81
/bin/stream_child line </out/stream.in >/out/stream.log 2>&1 || exit 82
/bin/stream_child line </out/stream.in >>/out/stream.log 2>&1 || exit 83
check() {
    IFS= read -r a && IFS= read -r b && IFS= read -r c && IFS= read -r d &&
      test "$a/$b/$c/$d" = 'file input/stream stderr/file input/stream stderr' &&
      ! IFS= read -r extra
}
check </out/stream.log || exit 84
/bin/stream_child closed-out 1>&- || exit 85
/usr/bin/dash -c 'IFS= read -r line && printf "%s\n" "$line"' </out/stream.in >/out/legacy.txt || exit 86
printf 'DASH_GLIBC_REDIRECT_PASS\n'
'''
EXTERNAL_HEREDOC = r'''exec 0<&-
value=expanded
value=inner /bin/stream_child line >/out/heredoc.log 2>&1 <<EOF || exit 81
external:$value
EOF
test "$value" = expanded || exit 87
/bin/stream_child line >>/out/heredoc.log 2>&1 <<'EOF' || exit 82
external:$value
EOF
check() {
    IFS= read -r a && IFS= read -r b && IFS= read -r c && IFS= read -r d &&
      test "$a/$b/$c/$d" = 'external:expanded/stream stderr/external:$value/stream stderr' &&
      ! IFS= read -r extra
}
check </out/heredoc.log || exit 83
printf 'DASH_GLIBC_EXTERNAL_HERE_PASS\n'
'''
CASES = {
    'builtins': (BUILTINS, 0, b'DASH_GLIBC_BUILTINS_PASS', ' alpha'),
    'files': (FILES, 0, b'DASH_GLIBC_FILES_PASS', ''),
    'pipeline': (PIPELINE, 0, b'DASH_GLIBC_PIPE_PASS', ''),
    'pipeline_printf': ("printf '%10037s' '' | /bin/stream_child spaces\n",
                        0, b'DASH_GLIBC_STREAM_BYTES=10037', ''),
    'pipeline_status': (PIPE_STATUS, 0, b'DASH_GLIBC_PIPE_STATUS_PASS', ''),
    'pipeline_redirect': (PIPE_REDIRECT, 0, b'DASH_GLIBC_PIPE_FILE_PASS', ''),
    'pipeline_closed': (PIPE_CLOSED, 0, b'DASH_GLIBC_PIPE_CLOSED_PASS', ''),
    'pipeline_failure': (PIPE_FAILURE, 0, b'DASH_GLIBC_PIPE_RECOVERED=8', ''),
    'pipeline_builtin': ("printf unexpected | printf unexpected\n",
                         2, b'C1 pipeline requires external commands', ''),
    'subshell': ("(printf unexpected)\n", 2, b'subshells unavailable', ''),
    'substitution': (SUBSTITUTION, 0, b'DASH_GLIBC_SUBSTITUTION_PASS', ''),
    'substitution_stream': (SUBSTITUTION_STREAM, 0, b'DASH_GLIBC_SUBSTITUTION_STREAM_PASS', ''),
    'substitution_close': (SUBSTITUTION_CLOSE, 0, b'DASH_GLIBC_SUBSTITUTION_CLOSE_PASS', ''),
    'substitution_denied': ('test -z "$(printf unexpected)"\n', 2, b'Operation not permitted', ''),
    'fork_runtime': ('/bin/fork_runtime\n', 0, b'DASH_GLIBC_FORK_RUNTIME_PASS', ''),
    'heredoc': (HEREDOC, 0, br'DASH_GLIBC_HERE_PASS <literal $word \keep> <expanded:expanded:12>', ''),
    'heredoc_failure': (HEREDOC_FAILURE, 0, b'DASH_GLIBC_HERE_RECOVERED=24', ''),
    'external_heredoc': (EXTERNAL_HEREDOC, 0, b'DASH_GLIBC_EXTERNAL_HERE_PASS', ''),
    'external_redirect': (REDIRECT, 0, b'DASH_GLIBC_REDIRECT_PASS', ''),
    'unmarked_redirect': (EXTERNAL.format(
        command="/bin/preview_child explicit 'two words' '' >/out/unmarked"),
                          126, b'Not supported', ''),
    'external_explicit': (EXPLICIT, 0, b'DASH_GLIBC_CHILD_EXPLICIT argv_env_cwd=ok', ''),
    'external_path': (EXTERNAL.format(command="preview_child path 'two words' ''"),
                      23, b'DASH_GLIBC_CHILD_PATH argv_env_cwd=ok', ''),
    'external_missing': (EXTERNAL.format(command='missing_tool'), 127, b'missing_tool:', ''),
    'external_text': (EXTERNAL.format(command='/bin/text_tool'), 126, b'Exec format error', ''),
    'authority_denied': (EXPLICIT, 126, b'Operation not permitted', ''),
}
EXTERNAL_CASES = {'external_explicit', 'external_path', 'external_missing',
                  'external_text', 'authority_denied', 'unmarked_redirect'}
RESTRICTED_CASES = {'authority_denied', 'substitution_denied'}


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


def build_programs(args, report):
    fixtures = ROOT / 'tests/fixtures/glibc_g3'
    child_source = fixtures / 'dash_external_child.c'
    stream_source = fixtures / 'dash_stream_child.c'
    fork_source = fixtures / 'dash_fork_runtime.c'
    launcher_source = fixtures / 'dash_without_create.cpp'
    child = args.artifacts / 'preview_child.elf'
    stream = args.artifacts / 'stream_child.elf'
    fork = args.artifacts / 'fork_runtime.elf'
    launcher = args.artifacts / 'preview_without_create.elf'
    sdk = args.system / 'sdk'
    compiler = tool('g++')
    commands = [
        [sys.executable, ROOT / 'scripts/build_glibc_program.py', '--sdk', args.glibc_sdk / 'sysroot',
         '--source', child_source, '--output', child],
        [sys.executable, ROOT / 'scripts/build_glibc_program.py', '--sdk', args.glibc_sdk / 'sysroot',
         '--source', stream_source, '--output', stream],
        [sys.executable, ROOT / 'scripts/build_glibc_program.py', '--sdk', args.glibc_sdk / 'sysroot',
         '--source', fork_source, '--output', fork],
        [compiler, *COMMON_FLAGS, *X86_FLAGS, '-I', sdk / 'include', '-nostdlib', '-static', '-no-pie',
         '-Wl,--build-id=none,--no-undefined,-z,noexecstack,-z,max-page-size=4096',
         '-T', sdk / 'user.ld', sdk / 'crt0.o', launcher_source, '-Wl,--start-group',
         sdk / 'lib/libxos.a', sdk / 'lib/libxos_loader.a', '-Wl,--end-group', '-o', launcher],
    ]
    with (args.artifacts / 'build-programs.log').open('w') as log:
        for invocation in commands:
            subprocess.run(invocation, check=True, stdout=log, stderr=subprocess.STDOUT)
    report['programs'] = {
        binary.name: {'sha256': sha(binary), 'source_sha256': sha(source)}
        for binary, source in ((child, child_source), (stream, stream_source), (fork, fork_source),
                               (launcher, launcher_source))
    }
    return child, stream, fork, launcher


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
        child, stream, fork, launcher = build_programs(args, report)
        with tempfile.TemporaryDirectory(prefix='xos_dash_glibc_') as folder:
            work = Path(folder)
            disk = work / 'work.img'
            create_fat32(disk, 512)
            install(disk, args.legacy_receipt)
            install(disk, args.preview_receipt, '/bin/dash_glibc')
            transfer(disk, 'import', '/bin/preview_child', child)
            transfer(disk, 'import', '/bin/stream_child', stream)
            transfer(disk, 'import', '/bin/fork_runtime', fork)
            transfer(disk, 'import', '/bin/preview_without_create', launcher)
            transfer(disk, 'import', '/bin/terminal.elf', args.system / 'user_terminal.image.elf')
            text_tool = args.artifacts / 'text_tool'
            text_tool.write_text('printf "DASH_GLIBC_TEXT_EXECUTED\\n"\n')
            report['fixtures'][text_tool.name] = sha(text_tool)
            transfer(disk, 'import', '/bin/text_tool', text_tool)
            for path in ('/cases', '/out'):
                transfer(disk, 'mkdir', path)
            fixtures = {'dot.inc': 'source_marker=DASH_GLIBC_FILES_PASS\n'}
            for name, (source, _, _, arguments) in CASES.items():
                fixtures[name + '.sh'] = source
                launcher = '/bin/preview_without_create' if name in RESTRICTED_CASES else '/bin/dash_glibc'
                fixtures['via_dash_' + name + '.sh'] = (
                    f'{launcher} /cases/{name}.sh{arguments}\nstatus=$?\n'
                    'printf "DASH_GLIBC_EXIT=%s\\n" "$status"\nexit "$status"\n')
            for name, source in fixtures.items():
                path = args.artifacts / name
                path.write_text(source)
                report['fixtures'][name] = sha(path)
                transfer(disk, 'import', '/cases/' + name, path)
            report['reserved_before'] = reserved_snapshot(disk)
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
                    if shell == 'xsh':
                        entry = ('exec-file /bin/dash_glibc'
                                 if name in RESTRICTED_CASES else '/bin/dash_glibc')
                        line = f'{entry} /cases/{name}.sh{arguments}'
                    else:
                        line = f'dash /cases/via_dash_{name}.sh'
                    began = time.monotonic()
                    capture = command(guest, line, b'[wait] pid=', timeout=120)
                    record = {'case': name, 'shell': shell, 'output': capture.decode(errors='replace'),
                              'elapsed_seconds': time.monotonic() - began}
                    report['runs'].append(record)
                    waited = re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', capture)
                    expected = str(status).encode()
                    assert waited == [(b'exited', expected)] and marker in capture, capture
                    assert b'getcwd() failed' not in capture, capture
                    if shell == 'dash':
                        assert b'DASH_GLIBC_EXIT=' + expected + b'\n' in capture, capture
                    if name == 'heredoc_failure':
                        assert capture.count(b'/missing/heredoc-output') == 24, capture
                    if name in EXTERNAL_CASES:
                        assert b'DASH_GLIBC_CHILD_RC=' + expected + b'\n' in capture, capture
                        assert b'DASH_GLIBC_TEXT_EXECUTED' not in capture and b'DASH_GLIBC_CHILD_BAD' not in capture, capture
                        if name in ('external_missing', 'external_text', 'authority_denied', 'unmarked_redirect'):
                            assert b'argv_env_cwd=ok' not in capture, capture
                    elif status:
                        assert b'unexpected' not in capture and b'DASH_GLIBC_BUILTINS_PASS' not in capture, capture
                    after = resources(guest)
                    assert after == baseline, (baseline, after)
                    record.update(exit_code=status, resources=after)
                    print(f'PASS {shell} {name} ({record["elapsed_seconds"]:.2f}s)', flush=True)
            start = len(guest.output)
            send_bytes(guest, b'/bin/dash_glibc -i\r')
            guest.expect(b'$ ', start=start, timeout=60)
            start = len(guest.output)
            send_bytes(guest, b'echo "$(printf \'DASH_GLIBC_%s\' INTERACTIVE_CAPTURE)"\r')
            guest.expect(b'DASH_GLIBC_INTERACTIVE_CAPTURE', start=start, timeout=60)
            start = len(guest.output)
            send_bytes(guest, b'exit\r')
            guest.expect_supervisor(start=start, timeout=60)
            assert resources(guest) == baseline
            report['interactive_substitution'] = 'passed'
            print('PASS interactive substitution', flush=True)
            terminal = command(guest, 'tty-run /bin/dash_glibc /cases/builtins.sh alpha',
                               b'kind=exited code=', timeout=90)
            assert b'DASH_GLIBC_BUILTINS_PASS' in terminal and b'kind=exited code=0' in terminal, terminal
            terminal_baseline = resources(guest)
            terminal = command(guest, 'tty-run /bin/dash_glibc /cases/substitution.sh',
                               b'kind=exited code=', timeout=90)
            assert re.findall(rb'\[wait\] pid=\d+ kind=(\w+) code=(-?\d+)', terminal) == [
                (b'exited', b'0')]
            assert b'DASH_GLIBC_SUBSTITUTION_PASS' in terminal, terminal
            terminal_after = resources(guest)
            assert terminal_after == terminal_baseline
            report['terminal_substitution'] = {'status': 'passed', 'baseline': terminal_baseline,
                                               'after': terminal_after}
            print('PASS terminal service substitution', flush=True)
            command(guest, 'sync', b'[files] sync=ok')
            guest.close()
            report['reserved_after'] = reserved_snapshot(disk)
            assert report['reserved_after'] == report['reserved_before'], report['reserved_after']
            exported = args.artifacts / 'files.txt'
            transfer(disk, 'export', '/out/files.txt', exported)
            assert exported.read_bytes() == b'glibc dash file bytes\n'
            evidence = {
                'pipeline.bin': bytes(position % 251 for position in range(10037)),
                'stream.log': b'file input\nstream stderr\n' * 2,
                'heredoc.log': b'external:expanded\nstream stderr\nexternal:$value\nstream stderr\n',
                'legacy.txt': b'file input\n',
                'unmarked': b'',
                'fork-shared.txt': b'abc',
                'substitution.in': b'file input\n',
            }
            report['redirected_files'] = {}
            for name, expected in evidence.items():
                path = args.artifacts / name
                transfer(disk, 'export', '/out/' + name, path)
                assert path.read_bytes() == expected, name
                report['redirected_files'][name] = sha(path)
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
