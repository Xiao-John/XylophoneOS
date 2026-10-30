# SPDX-License-Identifier: Apache-2.0
"""Build the separate E13-T SDK from a verified multithread newlib prefix.

Experimental until threading_pthread_smoke.py and threading_cpp_smoke.py pass.
The ordinary build/sdk and published SDKs are never overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def tree_fingerprint(root):
    entries = {}
    for path in sorted(root.rglob('*')):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            entries[relative] = 'symlink:' + os.readlink(path)
        elif path.is_file():
            entries[relative] = sha(path)
    return {'files': len(entries), 'sha256': hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--newlib-prefix', required=True, type=Path)
    parser.add_argument('--gcc-source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/threading_sdk')
    parser.add_argument('--cpp', action='store_true')
    parser.add_argument('--jobs', type=int, default=8, help='positive parallel build job count (default: 8)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    prefix = args.newlib_prefix.resolve()
    if args.cpp and args.gcc_source is None:
        parser.error('--gcc-source is required with --cpp')
    gcc = args.gcc_source.resolve(strict=True) if args.gcc_source else None
    if gcc is not None and (gcc / 'gcc/BASE-VER').read_text().strip() != '16.2.0':
        raise SystemExit('The threading runtime requires the frozen GCC 16.2.0 source')
    verified_newlib = json.loads((prefix.parent / 'receipt.json').read_text())
    for name in ['libc.a', 'libm.a']:
        if verified_newlib['artifacts']['x86_64-elf/lib/' + name] != sha(prefix / 'x86_64-elf/lib' / name):
            raise SystemExit('newlib archive differs from its build receipt')
    owned_inputs = [*sorted((ROOT / 'src/shared/include').rglob('*.hpp')),
                    *sorted((ROOT / 'src/user').rglob('*.hpp')),
                    *sorted((ROOT / 'src/user/include').rglob('*.h')),
                    *sorted((ROOT / 'src/user/threading/include').rglob('*.h')),
                    *sorted((ROOT / 'src/user').rglob('*.cpp')),
                    ROOT / 'scripts/build_threading_sdk.py', ROOT / 'scripts/build_threading_newlib.py',
                    ROOT / 'scripts/build.py', ROOT / 'scripts/toolchain.py', ROOT / 'scripts/user_build.py',
                    ROOT / 'src/ports/gcc/patches/0008-xos-thread-clock-boundary.patch',
                    ROOT / 'src/user/threading/compile.py', ROOT / 'src/user/arch/x86_64/user.ld',
                    ROOT / 'src/user/arch/x86_64/start.asm']
    initial_inputs = {str(p.relative_to(ROOT)): sha(p) for p in owned_inputs}
    chrono_source = gcc / 'libstdc++-v3/src/c++11/chrono.cc' if args.cpp else None
    if args.cpp and '__XOS_NO_WALL_CLOCK__' not in chrono_source.read_text():
        subprocess.run(['patch', '-p1', '-i', str(ROOT / 'src/ports/gcc/patches/0008-xos-thread-clock-boundary.patch')], cwd=gcc, check=True)
    gcc_tree_before = tree_fingerprint(gcc) if args.cpp else None
    if args.output.is_symlink():
        raise SystemExit('Refusing a symlinked SDK output directory')
    output = args.output.resolve()
    if output != ROOT / 'build' and ROOT / 'build' not in output.parents:
        raise SystemExit('output directory must be build/ or one of its subdirectories')
    if output.is_symlink():
        raise SystemExit('Refusing a symlinked SDK output directory')
    output.mkdir(parents=True, exist_ok=True)
    logs = ROOT / 'build/threading_sdk_logs'
    logs.mkdir(exist_ok=True)
    commands = []
    def run(command, name, cwd=None, env=None):
        commands.append([str(s) for s in command])
        with (logs / name).open('w') as log:
            subprocess.run(command, cwd=cwd, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
    cross = shutil.which('x86_64-elf-g++')
    assert subprocess.check_output([cross, '-dumpfullversion'], text=True).strip() == '16.2.0'
    newlib = prefix / 'x86_64-elf'
    config = (newlib / 'include/newlib.h').read_text()
    if '#define _RETARGETABLE_LOCKING 1' not in config:
        raise SystemExit('The supplied newlib is not configured for retargetable locking')
    for folder in ['include', 'lib']:
        (output / folder).mkdir(exist_ok=True)
    shutil.copytree(newlib / 'include', output / 'include', dirs_exist_ok=True)
    for name in ['libc.a', 'libm.a']:
        shutil.copyfile(newlib / 'lib' / name, output / 'lib' / name)
    for folder in ['src/shared/include/xos', 'src/user/include/xos']:
        shutil.copytree(ROOT / folder, output / 'include/xos', dirs_exist_ok=True)
    for header in (ROOT / 'src/user/include').glob('*.h'):
        shutil.copyfile(header, output / 'include' / header.name)
    shutil.copytree(ROOT / 'src/user/threading/include', output / 'include', dirs_exist_ok=True)
    with (output / 'include/newlib.h').open('a') as header:
        header.write('\n/* XOS E13-T profile: matching archives use __getreent. */\n#define __DYNAMIC_REENT__ 1\n')
    with (output / 'include/time.h').open('a') as header:
        header.write('\n#ifndef CLOCK_MONOTONIC\n#define CLOCK_MONOTONIC 4\n#endif\n'
                     '#ifdef __cplusplus\nextern "C" {\n#endif\n'
                     'int clock_gettime(clockid_t, struct timespec*);\n'
                     'int clock_getres(clockid_t, struct timespec*);\n'
                     'int nanosleep(const struct timespec*, struct timespec*);\n'
                     '#ifdef __cplusplus\n}\n#endif\n')
    shutil.copyfile(ROOT / 'src/user/threading/compile.py', output / 'compile.py')
    shutil.copyfile(ROOT / 'src/user/arch/x86_64/user.ld', output / 'user.ld')
    with (output / 'user.ld').open('a') as linker:
        linker.write('\nASSERT(__xos_image_end <= 0x5fe00000, "thread profile image overlaps reserved arena")\n')
    for name in ['LICENSE', 'NOTICE']:
        shutil.copyfile(ROOT / name, output / name)
    shutil.copytree(ROOT / 'licenses', output / 'licenses', dirs_exist_ok=True)
    shutil.copyfile(ROOT / 'src/third_party/newlib/COPYING.NEWLIB', output / 'COPYING.NEWLIB')
    run(['nasm', '-f', 'elf64', '-g', '-F', 'dwarf', '-DXOS_POSIX_MAIN=1',
         str(ROOT / 'src/user/arch/x86_64/start.asm'), '-o', str(output / 'crt0_posix.o')], 'crt.log')
    objects = output / 'objects'
    objects.mkdir(exist_ok=True)
    sdk_tools = ROOT / '.cache/xos_seed/threading_sdk_tools'
    sdk_tools.mkdir(exist_ok=True, parents=True)
    for name in ['as', 'ld']:
        if not (sdk_tools / name).exists():
            (sdk_tools / name).symlink_to(shutil.which('x86_64-elf-' + name))
    flags = ['-B' + str(sdk_tools) + '/', '-std=c++20' , '-O2', '-g', '-ffreestanding', '-fno-rtti', '-fno-stack-protector',
             '-fno-pic', '-fno-pie', '-mno-red-zone', '-march=x86-64', '-mcmodel=small',
             '-ftls-model=local-exec', '-DXOS_THREADED_RUNTIME', '-nostdinc++',
             '-I' + str(output / 'include')]
    sources = [*sorted((ROOT / 'src/user/libc').glob('*.cpp')),
               ROOT / 'src/user/sdk/file_client.cpp', ROOT / 'src/user/sdk/text.cpp',
               ROOT / 'src/user/arch/x86_64/syscall.cpp', ROOT / 'src/user/arch/x86_64/tls.cpp',
               ROOT / 'src/shared/runtime/memory.cpp',
               *sorted((ROOT / 'src/user/loader').glob('*.cpp')),
               *sorted((ROOT / 'src/user/threading').glob('*.cpp')),
               ROOT / 'src/user/arch/x86_64/thread_context.cpp']
    compiled = []
    for source in sources:
        target = objects / (str(source.relative_to(ROOT)).replace('/', '_') + '.o')
        # pthread_once must unwind its in-progress marker if an initializer throws.
        extra = ['-fexceptions', '-funwind-tables'] if source.name == 'pthread.cpp' else ['-fno-exceptions']
        run([cross, *flags, *extra, '-c', str(source), '-o', str(target)], source.stem + '.log')
        compiled.append(target)
    archive = output / 'lib/libxos.a'
    if archive.exists():
        archive.unlink()
    run(['x86_64-elf-ar', 'rcsD', str(archive), *map(str, compiled)], 'archive.log')
    # Keep the C++ configuration in a private, separate target runtime build.
    if args.cpp:
        work = ROOT / '.cache/xos_seed/threading_cpp'
        build = work / 'libstdcxx_build'
        (work / 'libgcc').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(gcc / 'libgcc/gthr-posix.h', work / 'libgcc/gthr-default.h')
        build.mkdir(exist_ok=True)
        env = os.environ.copy()
        env.pop('COMPILER_PATH', None)  # Host configure helpers use the native linker.
        target_tools = work / 'target_tools'
        target_tools.mkdir(exist_ok=True)
        for name in ['as', 'ld']:
            if not (target_tools / name).exists():
                (target_tools / name).symlink_to(shutil.which('x86_64-elf-' + name))
        binutils = str(target_tools.resolve()) + '/'
        env.update(CC='x86_64-elf-gcc -B' + binutils,
                   CXX='x86_64-elf-g++ -B' + binutils,
                   AR='x86_64-elf-ar', RANLIB='x86_64-elf-ranlib',
                   CFLAGS='-O2 -g -mno-red-zone -I' + str(output / 'include'),
                   CXXFLAGS='-O2 -g -mno-red-zone -fno-pie -fno-pic -D__XOS_NO_WALL_CLOCK__ -I' + str(output / 'include'),
                   gcc_cv_target_thread_file='posix', ac_cv_func_fcntl='yes', ac_cv_func_getexecname='no', ac_cv_func___cxa_thread_atexit='yes')
        run([str(gcc / 'libstdc++-v3/configure'), '--host=x86_64-elf',
             '--prefix=' + str(output / 'cpp'), '--with-gxx-include-dir=' + str(output / 'cpp/include'),
             '--disable-multilib', '--disable-shared', '--disable-nls', '--with-newlib',
             '--disable-libstdcxx-pch', '--enable-libstdcxx-threads=yes',
             '--disable-libstdcxx-backtrace', '--disable-libstdcxx-filesystem-ts'],
            'cpp_configure.log', cwd=build, env=env)
        # Bare-metal newlib defaults do not discover XOS-provided functions.
        # These are actual SDK implementations, qualified by the guest gates.
        feature_defines = ['HAVE_SYS_TIME_H', 'HAVE___CXA_THREAD_ATEXIT', '_GLIBCXX_USE_CLOCK_MONOTONIC', '_GLIBCXX_USE_NANOSLEEP']
        config_path = build / 'config.h'
        config_text = config_path.read_text()
        for define in feature_defines:
            config_text = config_text.replace('/* #undef ' + define + ' */', '#define ' + define + ' 1')
        config_path.write_text(config_text)
        # include/c++config.h must reflect the same feature configuration.
        generated = build / 'include/x86_64-elf/bits/c++config.h'
        if generated.exists():
            generated.unlink()
        feature_stamp = build / '.xos_features_sha256'
        feature_sha = hashlib.sha256((config_text + env['CXXFLAGS'] + chrono_source.read_text()).encode()).hexdigest()
        if not feature_stamp.exists() or feature_stamp.read_text() != feature_sha:
            run(['make', 'clean'], 'cpp_clean_config_change.log', cwd=build, env=env)
            feature_stamp.write_text(feature_sha)
        run(['make', '-j' + str(args.jobs)], 'cpp_make.log', cwd=build, env=env)
        feature_stamp.write_text(feature_sha)
        run(['make', 'install'], 'cpp_install.log', cwd=build, env=env)
        compiler_build = work / 'gcc'
        compiler_build.mkdir(exist_ok=True)
        native = os.environ.copy()
        native.pop('COMPILER_PATH', None)
        run([str(gcc / 'gcc/configure'), '--target=x86_64-elf', '--disable-multilib',
             '--disable-nls', '--enable-languages=c,c++', '--enable-threads=posix'],
            'gcc_headers_configure.log', cwd=compiler_build, env=native)
        # Generate configuration only; the installed compiler supplies codegen.
        run(['make', '-o', 'specs', '-o', 'xgcc', 'libgcc.mvars', 'tconfig.h'],
            'gcc_headers_make.log', cwd=compiler_build, env=native)
        plugin = Path(subprocess.check_output([cross, '-print-file-name=plugin'], text=True).strip()) / 'include'
        for header in plugin.rglob('*'):
            target = compiler_build / header.relative_to(plugin)
            if header.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(header, target)
        unwind_build = work / 'libgcc_build'
        unwind_build.mkdir(exist_ok=True)
        run([str(gcc / 'libgcc/configure'), '--host=x86_64-elf', '--disable-shared',
             '--disable-gcov', '--prefix=' + str(output / 'cpp')],
            'libgcc_configure.log', cwd=unwind_build, env=env)
        members = ['unwind-dw2.o', 'unwind-dw2-fde.o', 'unwind-sjlj.o', 'unwind-c.o', 'emutls.o']
        run(['make', '-j' + str(args.jobs), 'gcc_objdir=' + str(compiler_build), *members],
            'libgcc_make.log', cwd=unwind_build, env=env)
        libgcc = output / 'cpp/lib/libgcc.a'
        original = Path(subprocess.check_output([cross, '-print-libgcc-file-name'], text=True).strip())
        shutil.copyfile(original, libgcc)
        run(['x86_64-elf-ar', 'rcsD', str(libgcc), *[str(unwind_build / name) for name in members]], 'libgcc_archive.log')
        for name in ['COPYING3', 'COPYING.RUNTIME']:
            shutil.copyfile(gcc / name, output / 'licenses' / ('gcc-' + name))
    final_inputs = {str(p.relative_to(ROOT)): sha(p) for p in owned_inputs}
    gcc_tree_after = tree_fingerprint(gcc) if args.cpp else None
    if args.cpp and gcc_tree_before != gcc_tree_after:
        raise SystemExit('GCC source tree changed during the runtime build')
    if final_inputs != initial_inputs:
        raise SystemExit('SDK inputs changed during the build; retry with a stable source snapshot')
    receipt = {'profile': 'xos-threading-v1-experimental', 'abi': 1, 'thread_abi': 1,
               'display_extensions': {'version': 1, 'syscalls': [65, 66], 'pixel_format': 'XRGB8888', 'surface_count': 1},
               'process_extensions': {'syscalls': list(range(54,62)), 'file_operations': [20,21,22],
                   'startup_versions': [1,2,3], 'exec_image_abi': 3, 'exec_marker': '.xos.exec',
                   'fork_supported': False, 'exec_supported': False, 'fd_count': 32,
                   'pipe_atomic_bytes': 4096, 'pipe_wait_write_minimum': True, 'pipe_atomic_flag': '0x8000000000000000'},
               'qualification': 'not_run', 'commands': commands,
               'inputs': initial_inputs,
               'newlib_build_receipt_sha256': sha(prefix.parent / 'receipt.json'),
               'gcc_source_archive_sha256': (json.loads((ROOT / 'src/ports/gcc/source_lock.json').read_text())['sha256']
                                             if args.cpp else None),
               'gcc_chrono_source_sha256': sha(chrono_source) if args.cpp else None,
               'gcc_source_tree': gcc_tree_before,
               'compiler': {'path': cross, 'sha256': sha(cross), 'version': '16.2.0'},
               'base_libgcc_sha256': sha(original) if args.cpp else None,
               'newlib_input': {name: sha(newlib / 'lib' / name) for name in ['libc.a', 'libm.a']},
               'artifacts': {str(p.relative_to(output)): sha(p) for p in output.rglob('*') if p.is_file() and p.name != 'manifest.json'}}
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Built experimental threading SDK:', output)

if __name__ == '__main__':
    main()
