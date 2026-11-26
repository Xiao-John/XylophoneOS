# SPDX-License-Identifier: Apache-2.0
"""Build dash C3 for newlib or an explicit static glibc preview."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import shlex
import struct

from glibc_g1_probe import clean_build_environment, tool_identity
from xypm_format import load_json
from xypm_sdk_profile import verify_profile

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT/'src/ports/dash'
SYSCALL = ROOT/'src/user/arch/x86_64/syscall.cpp'
NATIVE_INCLUDES = (ROOT/'src/user/include', ROOT/'src/shared/include')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, default=ROOT/'build/sdk')
    parser.add_argument('--glibc-profile', type=Path, help='verify and use an explicit glibc candidate sysroot')
    parser.add_argument('--archive', type=Path, default=ROOT/'src/ports/dash/upstream/dash-0.5.13.5.tar.gz')
    parser.add_argument('--receipt', type=Path, help='write this build receipt to an explicit consumer path')
    a = parser.parse_args()
    if not a.archive.exists():
        parser.error(f'dash archive not found: {a.archive}')
    sdk, archive = a.sdk.resolve(strict=True), a.archive.resolve(strict=True)
    glibc = a.glibc_profile is not None
    manifest_path = sdk.parent/'manifest.json' if glibc else sdk/'manifest.json'
    binding, tools = None, {}
    if glibc:
        if a.sdk.name != 'sysroot' or a.sdk.is_symlink():
            parser.error('--glibc-profile requires the SDK build sysroot directory')
        try:
            binding = verify_profile(load_json(a.glibc_profile), 'glibc', a.sdk.parent)
            metadata = load_json(manifest_path)
            for name in ('gcc', 'g++', 'as', 'ld'):
                executable = 'x86_64-elf-' + name
                tool = tool_identity(executable)
                if tool.get('sha256') != metadata['tools'][executable]['sha256']:
                    parser.error(executable + ' differs from the SDK build')
                tools[name] = tool
        except (ValueError, OSError, KeyError, TypeError) as error:
            parser.exit(1, 'dash glibc profile: ' + str(error) + '\n')
    lock = json.loads((PORT/'source_lock.json').read_text())
    if sha(archive) != lock['sha256']: parser.error('dash archive hash mismatch')
    inputs = {str(p.relative_to(ROOT)):sha(p) for p in sorted(PORT.rglob('*')) if p.is_file()}
    inputs['scripts/build_dash.py'] = sha(__file__)
    inputs.update({'sdk/'+str(p.relative_to(sdk)):sha(p) for p in sorted(sdk.rglob('*')) if p.is_file()})
    if glibc:
        inputs['sdk/manifest.json'] = sha(manifest_path)
        inputs['profile'] = binding['profile_sha256']
        native_inputs = [SYSCALL]
        native_inputs.extend(path for directory in NATIVE_INCLUDES for path in directory.rglob('*.hpp'))
        inputs.update({str(path.relative_to(ROOT)): sha(path) for path in native_inputs})
    key = hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()[:20]
    cache_namespace = 'dash_glibc_preview' if glibc else 'dash'
    work = ROOT/'.cache/xos_seed'/cache_namespace/key
    work.mkdir(parents=True,exist_ok=True)
    source = work/'source'
    if not source.exists():
        source.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                parts = Path(member.name).parts
                if '..' in parts or Path(member.name).is_absolute() or member.issym() or member.islnk():
                    raise ValueError('unsafe source archive member')
                member.name = str(Path(*parts[1:]))
                if member.name != '.':
                    try:
                        tar.extract(member,source,filter='data')
                    except TypeError:
                        tar.extract(member,source)
        if not (source/'configure').is_file():
            raise SystemExit(f'dash extraction produced no configure under {source}')
        for patch in sorted((PORT/'patches').glob('*.patch')):
            subprocess.run(['patch','-p1','-i',str(patch)],cwd=source,check=True,stdout=subprocess.DEVNULL)
        for local, upstream in (('jobs_xos.c','jobs.c'),('signals_xos.c','trap.c')):
            shutil.copyfile(PORT/local,source/'src'/upstream)
        with (source/'src/eval.c').open('a') as stream:stream.write('\n'+(PORT/'admission_xos.c').read_text())
    build = work/'build';build.mkdir(exist_ok=True)
    cc = os.environ.get('XOS_CC',shutil.which('x86_64-elf-gcc') or 'x86_64-elf-gcc')
    cxx = os.environ.get('XOS_CXX',shutil.which('x86_64-elf-g++') or 'x86_64-elf-g++')
    env = dict(os.environ)
    if glibc:
        cc, cxx = tools['gcc']['path'], tools['g++']['path']
        env, _ = clean_build_environment(env)
        env['LC_ALL'] = 'C'
    target_tools = work/'target_tools'
    target_tools.mkdir(exist_ok=True)
    for name in ('as', 'ld'):
        link = target_tools/name
        selected = Path(tools[name]['path'] if glibc else shutil.which('x86_64-elf-'+name)).resolve()
        if not link.is_symlink():
            link.symlink_to(selected)
        elif glibc and link.resolve(strict=True) != selected:
            parser.error('cached target tool differs from ' + name)
    flags = ['-B'+str(target_tools)+'/', '-O2','-mno-red-zone','-fno-pie','-fno-pic','-fno-stack-protector','-ffunction-sections','-fdata-sections']
    bridge = work/'console_xos.o'
    cppflags = ['-DJOBS=0', '-include', str(PORT/'xos_profile.h')]
    ldflags = ['-nostdlib', '-static', '-no-pie', '-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
               '-T', str(sdk/'user.ld')]
    host_cc = shutil.which('clang') or 'cc'
    host_system = 'aarch64-apple-darwin'
    if glibc:
        include, libdir = sdk/'usr/include', sdk/'usr/lib'
        flags += ['--sysroot='+str(sdk), '-nostdinc', '-isystem', str(include), '-isystem',
                  str(libdir/'compiler-include')]
        cppflags += ['-D_GNU_SOURCE=1', '-DXOS_DASH_GLIBC_PREVIEW=1']
        ldflags += [str(libdir/name) for name in ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o')]
        syscalls = work/'syscall.o'
        # Make only the native xos/ headers visible to the bridge sources.
        # src/user/include also has a newlib dirent.h compatibility header.
        headers = work/'native_headers'
        headers.mkdir(exist_ok=True)
        link = headers/'xos'
        if not link.is_symlink():
            link.symlink_to(NATIVE_INCLUDES[0]/'xos')
        elif link.resolve(strict=True) != NATIVE_INCLUDES[0]/'xos':
            parser.error('cached XOS native header location differs')
        cxx_flags = [cxx, *flags, '-nostdinc++', '-fno-exceptions', '-fno-rtti',
                     '-isystem', str(headers), '-isystem', str(NATIVE_INCLUDES[1])]
        for source_file, output in ((PORT/'console_xos.cpp', bridge), (SYSCALL, syscalls)):
            subprocess.run([*cxx_flags, '-c', str(source_file), '-o', str(output)], env=env, check=True)
        libs = [str(bridge), str(syscalls), '-Wl,--start-group',
                *[str(libdir/name) for name in ('libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a')],
                '-Wl,--end-group', str(libdir/'crtend.o'), str(libdir/'crtn.o')]
        host_system = subprocess.check_output([host_cc, '-dumpmachine'], env=env, text=True).strip()
    else:
        flags += ['-isystem', str(NATIVE_INCLUDES[0])]
        cppflags += ['-isystem', str(sdk/'include')]
        ldflags += ['-Wl,--gc-sections', str(sdk/'crt0_posix.o')]
        subprocess.run([cxx,*flags,'-fno-exceptions','-fno-rtti','-isystem',str(sdk/'include'),
                        '-c',str(PORT/'console_xos.cpp'),'-o',str(bridge)],check=True)
        libs = [str(bridge),'-Wl,--start-group',*[str(sdk/'lib'/n) for n in ('libxos.a','libxos_loader.a','libc.a','libm.a')],
                subprocess.check_output([cc,'-print-libgcc-file-name'],text=True).strip(),'-Wl,--end-group']
    env.update(CC=cc, CC_FOR_BUILD=host_cc, CFLAGS=shlex.join(flags), CPPFLAGS=shlex.join(cppflags),
               LDFLAGS=shlex.join(ldflags), LIBS=shlex.join(libs))
    def run(args,name):
        with (work/name).open('w') as log:
            result = subprocess.run(args,cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            print((work/name).read_text()[-7000:]);raise SystemExit(result.returncode)
    if not (build/'Makefile').exists():
        run([str(source/'configure'),'--build='+host_system,'--host=x86_64-unknown-elf','--without-libedit','--disable-glob','--disable-tee','--disable-memfd-create'],'configure.log')
    run(['make','-j2'],'make.log')
    debug_elf = build/'src/dash'
    elf = build/'src/dash.runtime'
    objcopy = None
    if glibc:
        # The glibc LOAD segment includes the ELF header. Removing debug
        # sections changes section metadata inside those mapped bytes.
        shutil.copyfile(debug_elf, elf)
    else:
        objcopy = shutil.which('x86_64-elf-objcopy')
        subprocess.run([objcopy, '--strip-debug', str(debug_elf), str(elf)], env=env, check=True)
    def load_segments(path):
        data = path.read_bytes()
        phoff = struct.unpack_from('<Q', data, 32)[0]
        phsize, phcount = struct.unpack_from('<HH', data, 54)
        result = []
        for index in range(phcount):
            kind, flags, offset, address, _, files, memory, alignment = struct.unpack_from('<IIQQQQQQ', data, phoff+index*phsize)
            if kind in (1, 7): result.append((kind, flags, address, files, memory, alignment, data[offset:offset+files]))
        return struct.unpack_from('<Q', data, 24)[0], result
    if load_segments(elf) != load_segments(debug_elf):
        raise SystemExit('debug stripping changed loaded bytes or the entry point')
    result = {'profile':'dash_glibc_preview' if glibc else 'dash_c3','version':lock['version'],'elf':str(elf.relative_to(ROOT)),'sha256':sha(elf),'bytes':elf.stat().st_size,'inputs':inputs,'status':'built_not_run','debug_elf':str(debug_elf.relative_to(ROOT)),'debug_sha256':sha(debug_elf),'load_segments_unchanged':True}
    if objcopy is not None:
        result['objcopy'] = {'path': objcopy, 'sha256': sha(objcopy), 'version':
                             subprocess.check_output([objcopy, '--version'], text=True).splitlines()[0]}
    result['receipt'] = str((work/'manifest.json').relative_to(ROOT))
    result['sdk_manifest_sha256'] = sha(manifest_path)
    if glibc:
        if verify_profile(load_json(a.glibc_profile), 'glibc', a.sdk.parent) != binding:
            raise RuntimeError('glibc profile changed during dash build')
        if (any(sha(ROOT/name) != hash_value for name, hash_value in inputs.items()
                if name != 'profile' and not name.startswith('sdk/'))
                or sha(archive) != lock['sha256']
                or any(sha(tool['path']) != tool['sha256'] for tool in tools.values())):
            raise RuntimeError('dash source or toolchain changed during build')
        result['sdk_profile_binding'] = binding
        result['target_tools'] = tools
    (work/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    if a.receipt:
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        a.receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k!='inputs'}))


if __name__=='__main__':main()
