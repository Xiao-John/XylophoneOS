# SPDX-License-Identifier: Apache-2.0
"""Compressed E08-post5 P1 runner: R1 repeat, R2 scale, R3 large input, R5 failures."""
from __future__ import annotations
import argparse, hashlib, json, re, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'tests')]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import command, resources
from seed_diagnostics import guest_command
from gcc_seed_smoke import (guest_tool, import_manifest_files, read_manifest, sha,
                            verify_current_sdk, validate_bundle)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed-manifest', type=Path, default=ROOT / 'build/cpp_bundle/seed_manifest.json')
    p.add_argument('--seed-root', type=Path, default=ROOT)
    p.add_argument('--sysroot-manifest', type=Path, default=ROOT / 'build/cpp_bundle/sysroot_manifest.json')
    p.add_argument('--sysroot-root', type=Path, default=ROOT)
    p.add_argument('--levels', default='r1,r2')
    p.add_argument('--cycles', type=int, default=10)
    p.add_argument('--report', type=Path, default=ROOT / 'build/e08_post5_p1_report.json')
    p.add_argument('--keep-image', action='store_true')
    a = p.parse_args()
    levels = {x.strip() for x in a.levels.split(',') if x.strip()}
    unknown = levels - {'r1', 'r2', 'r3', 'r5'}
    if unknown or not levels:
        p.error(f'unknown/empty levels: {unknown}')
    seed_manifest, seed = read_manifest(a.seed_manifest.resolve(), ('gcc', 'g++', 'cc1', 'cc1plus', 'as', 'ld', 'ar', 'ranlib'))
    pre = validate_bundle(a.seed_manifest.resolve(), a.seed_root.resolve(),
                          a.sysroot_manifest.resolve(), a.sysroot_root.resolve(), '/sysroot',
                          ('gcc', 'g++', 'cc1', 'cc1plus', 'as', 'ld', 'ar', 'ranlib'))
    if not pre.ok:
        raise SystemExit('preflight failed: ' + pre.summary)
    sdk_manifest = (ROOT / seed['sdk_manifest']).resolve()
    if sha(sdk_manifest) != seed['sdk_manifest_sha256']:
        raise AssertionError('SDK manifest provenance mismatch')
    sdk = verify_current_sdk(sdk_manifest, ROOT / 'build')
    system = json.loads((ROOT / 'build/manifest.json').read_text())
    report = {'schema_version': 1, 'gate': 'E08-post5-P1', 'status': 'failed',
              'build_id': system['build_id'], 'xos_sha256': sha(ROOT / 'build/xos.img'),
              'seed_manifest_sha256': sha(a.seed_manifest), 'sdk_manifest_sha256': sha(sdk_manifest),
              'sdk_files_sha256': sdk, 'levels': sorted(levels), 'checks': [],
              'commands': [], 'resource_samples': [], 'outputs': {}}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix='xos_post5_p1_') as folder:
            tmp = Path(folder); disk = tmp / 'p1.img'
            create_fat32(disk, 2048)
            for path in ('/bin', '/src', '/out', '/tmp'):
                transfer(disk, 'mkdir', path)
            report['seed_files'] = len(import_manifest_files(disk, a.seed_root, seed['install_files'], 'Seed'))
            sysroot_manifest = json.loads(a.sysroot_manifest.read_text())
            report['sysroot_files'] = len(import_manifest_files(disk, a.sysroot_root,
                                                                sysroot_manifest['files'], 'sysroot'))
            def put(name: str, text: str):
                src = tmp / name; src.write_text(text)
                transfer(disk, 'import', '/src/' + name, src)
            # R1 fixed three-TU baseline, repeated.
            put('p1_util.c', 'int p1_add(int a, int b) { return a + b; }\n')
            put('p1_main.c', '#include <stdio.h>\nint p1_add(int,int);\nint main(void){if(p1_add(20,22)!=42)return 1;puts("P1_R1_OK");return 0;}\n')
            # R2 16 C + 6 C++ translation units.
            cxx_names = []
            for i in range(16):
                put(f't{i:02d}.c', f'int t{i:02d}(void){{return {i};}}\n')
            calls = '+'.join(f't{i:02d}()' for i in range(16))
            put('r2_main.c', '#include <stdio.h>\n' + ''.join(f'int t{i:02d}(void);\n' for i in range(16)) +
                f'int main(void){{int v={calls};if(v!=120)return 1;printf("P1_R2_C=%d\\n",v);return 0;}}\n')
            for i in range(6):
                name = f'c{i:02d}.cpp'; cxx_names.append(name)
                put(name, '#include <string>\nstd::string f%d(void){return "x";}\n' % i)
            put('r2_main.cpp', '#include <cstdio>\n#include <string>\n' +
                ''.join(f'std::string f{i}(void);\n' for i in range(6)) +
                'int main(void){std::string s;' + ''.join(f's+=f{i}();' for i in range(6)) +
                'if(s!="xxxxxx")return 1;puts("P1_R2_CPP=ok");return 0;}\n')
            # R3 large source, BSS and deep include chain.
            put('big.c', ''.join(f'int big{i}(void){{return {i};}}\n' for i in range(12000)) +
                'int main(void){return big0()!=0;}\n')
            put('bss.c', '#include <stdio.h>\nchar bss[8*1024*1024];\nint main(void){bss[0]=1;bss[sizeof bss-1]=2;printf("P1_R3_BSS=ok\\n");return 0;}\n')
            for i in range(64):
                put(f'h{i:02d}.h', '#pragma once\n' + (f'#include "h{i-1:02d}.h"\n' if i else '') + f'#define H{i} {i}\n')
            put('deep.c', ''.join(f'#include "h{i:02d}.h"\n' for i in range(64)) + 'int main(void){return H63!=63;}\n')
            # R5 failure paths.
            put('bad_header.c', '#include <missing_post5.h>\nint main(void){return 0;}\n')
            put('bad_syntax.c', 'int main(void){ this is not C; }\n')
            put('undefined_link.c', 'int missing_post5_symbol(void);\nint main(void){return missing_post5_symbol();}\n')

            guest = boot(disk, f'e08_post5_p1_{__import__("os").getpid()}')
            baseline = resources(guest); report['baseline_resources'] = baseline
            gcc = guest_tool(seed, 'gcc'); gxx = guest_tool(seed, 'g++'); ar = guest_tool(seed, 'ar'); ranlib = guest_tool(seed, 'ranlib')
            sys = '--sysroot=/sysroot'

            def run(line: str, expected: int | None = 0, timeout=300):
                started = time.monotonic()
                supervisor_line = guest_command(line, (gcc, gxx))
                out = command(guest, supervisor_line, b'kind=exited code=', timeout=timeout)
                m = re.search(rb'kind=exited code=(-?\d+)', out)
                code = int(m.group(1)) if m else None
                cur = resources(guest)
                report['commands'].append({'line': line, 'supervisor_command': supervisor_line,
                                           'exit_code': code,
                                           'seconds': time.monotonic() - started,
                                           'resources': cur})
                report['resource_samples'].append({'line': line, 'resources': cur})
                if expected is not None and code != expected:
                    raise AssertionError(f'{line}: exit {code}, expected {expected}: {out[-1200:]!r}')
                if expected is None and code == 0:
                    raise AssertionError(f'{line}: expected failure but exited 0')
                if cur != baseline:
                    raise AssertionError(f'{line}: resource drift {cur} != {baseline}')
                return out

            if 'r1' in levels:
                for n in range(a.cycles):
                    run(f'{gcc} {sys} -I/src -c /src/p1_util.c -o /out/r1_util.o')
                    run(f'{gcc} {sys} -I/src -c /src/p1_main.c -o /out/r1_main.o')
                    run(f'{gcc} -static {sys} /out/r1_util.o /out/r1_main.o -o /out/r1_app.elf')
                    out = run('exec-file /out/r1_app.elf')
                    if b'P1_R1_OK' not in out:
                        raise AssertionError('R1 marker missing')
                report['checks'].append(f'R1 {a.cycles} cycles')

            if 'r2' in levels:
                for i in range(16):
                    run(f'{gcc} {sys} -I/src -c /src/t{i:02d}.c -o /out/t{i:02d}.o')
                run(f'{gcc} {sys} -I/src -c /src/r2_main.c -o /out/r2_main.o')
                run(f'{ar} rcS /out/libp1.a ' + ' '.join(f'/out/t{i:02d}.o' for i in range(16)))
                run(f'{ranlib} /out/libp1.a')
                run(f'{gcc} -static {sys} /out/r2_main.o /out/libp1.a -o /out/r2_c.elf')
                out = run('exec-file /out/r2_c.elf')
                if b'P1_R2_C=120' not in out: raise AssertionError('R2 C marker missing')
                for name in cxx_names:
                    run(f'{gxx} -std=gnu++17 {sys} -I/src -c /src/{name} -o /out/{name[:-4]}.o')
                run(f'{gxx} -std=gnu++17 {sys} -I/src -c /src/r2_main.cpp -o /out/r2_main_cpp.o')
                run(f'{gxx} -static {sys} ' + ' '.join(f'/out/{n[:-4]}.o' for n in cxx_names) +
                    ' /out/r2_main_cpp.o -o /out/r2_cpp.elf')
                out = run('exec-file /out/r2_cpp.elf')
                if b'P1_R2_CPP=ok' not in out: raise AssertionError('R2 C++ marker missing')
                report['checks'].append('R2 16C+6C+++archive')

            if 'r3' in levels:
                run(f'{gcc} {sys} -O0 -I/src -c /src/big.c -o /out/big.o')
                run(f'{gcc} -static {sys} /out/big.o -o /out/big.elf')
                run('exec-file /out/big.elf')
                run(f'{gcc} {sys} -I/src -c /src/bss.c -o /out/bss.o')
                run(f'{gcc} -static {sys} /out/bss.o -o /out/bss.elf')
                out = run('exec-file /out/bss.elf')
                if b'P1_R3_BSS=ok' not in out: raise AssertionError('R3 BSS marker missing')
                run(f'{gcc} {sys} -I/src -c /src/deep.c -o /out/deep.o')
                report['checks'].append('R3 1MiB source/8MiB BSS/64 includes')

            if 'r5' in levels:
                run(f'{gcc} {sys} -I/src -c /src/bad_header.c -o /out/bad.o', expected=None)
                run(f'{gcc} {sys} -I/src -c /src/bad_syntax.c -o /out/bad2.o', expected=None)
                run(f'{gcc} -static {sys} /src/undefined_link.c -o /out/undef.elf', expected=None)
                run(f'{gcc} -truncate /out/zero /out/r1_app.elf', expected=None)
                report['checks'].append('R5 four negative paths')

            report['status'] = 'passed'
            guest.close(); guest = None
            if a.keep_image:
                keep = ROOT / 'build/e08_post5_p1_last.img'
                disk.replace(keep)
                report['kept_image'] = str(keep)
            print(f"PASS: E08-post5 P1 {','.join(sorted(levels))}")
    except Exception as e:
        report['error'] = str(e); raise
    finally:
        if guest is not None: guest.close()
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
