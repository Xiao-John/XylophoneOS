# SPDX-License-Identifier: Apache-2.0
"""Build the pinned sbase Make serial, explicit -B profile against an XOS SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/make'
COMPILED_C = ('main.c', 'parser.c', 'rules.c', 'defaults.c')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool_info(command):
    located = shutil.which(command)
    path = Path(located if located else command).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path),
            'version': subprocess.check_output([str(path), '--version'], text=True).splitlines()[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=ROOT / 'build/sdk')
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    lock = json.loads((PORT / 'source_lock.json').read_text())
    expected_files = {'LICENSE', *('make/' + name for name in
                                  (*COMPILED_C, 'posix.c', 'make.h'))}
    if set(lock['files']) != expected_files:
        parser.error('source lock must bind all original Make files and the upstream LICENSE')
    for name, expected in lock['files'].items():
        source = PORT / 'upstream' / name
        if not source.is_file() or sha(source) != expected:
            parser.error('vendored sbase Make source mismatch: ' + name)
    cc = tool_info(os.environ.get('XOS_CC', 'x86_64-elf-gcc'))
    cxx = tool_info(os.environ.get('XOS_CXX', 'x86_64-elf-g++'))
    target_tools = ROOT / 'build/target_tools'
    tools = {'cc': cc, 'cxx': cxx}
    for name in ('as', 'ld'):
        target = target_tools / name
        if not target.is_file():
            parser.error('prepare build/target_tools/' + name + ' before building Make')
        tools[name] = tool_info(str(target))
    libgcc = Path(subprocess.check_output([cc['path'], '-print-libgcc-file-name'], text=True).strip()).resolve(strict=True)
    tools['libgcc'] = {'path': str(libgcc), 'sha256': sha(libgcc)}
    inputs = {str(path.relative_to(ROOT)): sha(path)
              for path in sorted(PORT.rglob('*')) if path.is_file()}
    inputs['scripts/build_make.py'] = sha(__file__)
    inputs.update({'sdk/' + str(path.relative_to(sdk)): sha(path)
                   for path in sorted(sdk.rglob('*')) if path.is_file()})
    fingerprint = hashlib.sha256(json.dumps({'inputs': inputs, 'tools': tools},
                                           sort_keys=True).encode()).hexdigest()[:20]
    work = ROOT / '.cache/xos_seed/make' / fingerprint
    source = work / 'source'
    source.mkdir(parents=True, exist_ok=True)
    # These are generated copies in this fingerprint's exclusive build area.
    # Never patch the vendored originals or install anything into a disk image.
    for name in (*COMPILED_C, 'make.h'):
        shutil.copyfile(PORT / 'upstream/make' / name, source / name)
    shutil.copyfile(PORT / 'upstream/LICENSE', work / 'LICENSE')
    commands = []
    with (work / 'build.log').open('w') as log:
        def run(command, cwd=work):
            commands.append(command)
            result = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                log.flush()
                (work / 'build_failure.json').write_text(json.dumps({
                    'status': 'build_failed', 'fingerprint': fingerprint,
                    'inputs': inputs, 'tools': tools, 'commands': commands,
                    'returncode': result.returncode}, indent=2) + '\n')
                raise SystemExit('Make build failed; inspect ' + str(work / 'build.log'))

        for patch in sorted((PORT / 'patches').glob('*.patch')):
            run(['patch', '-p1', '-i', str(patch)], cwd=source)
        flags = ['-B' + str(target_tools) + '/', '-O2', '-mno-red-zone', '-fno-pie',
                 '-fno-pic', '-fno-stack-protector', '-ffunction-sections', '-fdata-sections',
                 '-isystem', str(sdk / 'include'), '-I', str(source)]
        objects = []
        for name in COMPILED_C:
            output = work / (name + '.o')
            run([cc['path'], '-std=c11', *flags, '-c', str(source / name), '-o', str(output)])
            objects.append(str(output))
        backend = work / 'posix_xos.o'
        run([cxx['path'], '-std=c++17', *flags, '-fno-exceptions', '-fno-rtti',
             '-c', str(PORT / 'posix_xos.cpp'), '-o', str(backend)])
        elf = work / 'make'
        run([cc['path'], '-B' + str(target_tools) + '/', '-nostdlib', '-static', '-no-pie',
             '-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
             '-T', str(sdk / 'user.ld'), str(sdk / 'crt0_posix.o'), *objects, str(backend),
             '-Wl,--start-group', *(str(sdk / 'lib' / name) for name in
                                      ('libxos.a', 'libxos_loader.a', 'libc.a', 'libm.a')),
             str(libgcc), '-Wl,--end-group', '-o', str(elf)])
    report = {'status': 'built_not_run', 'profile': 'sbase_make_xos_explicit_always_build_v1',
              'commit': lock['commit'], 'tree': lock['tree'], 'fingerprint': fingerprint,
              'elf': str(elf.relative_to(ROOT)), 'guest_path': '/usr/bin/make',
              'sha256': sha(elf), 'bytes': elf.stat().st_size,
              'sdk_manifest_sha256': sha(sdk / 'manifest.json'),
              'inputs': inputs, 'tools': tools, 'commands': commands,
              'adapted_sources': {name: sha(source / name) for name in (*COMPILED_C, 'make.h')},
              'requires': ['explicit -B', 'real fork/execve', '/usr/bin/dash', 'spawn depth 2'],
              'upstream_license_sha256': sha(PORT / 'upstream/LICENSE')}
    (work / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ('inputs', 'tools', 'commands', 'adapted_sources')}))


if __name__ == '__main__':
    main()
