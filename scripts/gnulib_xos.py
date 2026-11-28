#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared, explicit XOS/glibc inputs for GNU packages using gnulib."""
import os
from pathlib import Path
import re
import shlex

from glibc_g1_probe import clean_build_environment
from xypm_format import require


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / 'src/ports/gnulib'
TARGET = 'x86_64-unknown-xos'


def target_site(metadata):
    """Disable actual SDK stubs, including their public spelling aliases.

    Autoconf link tests alone accept glibc's linkable ENOSYS stubs.  Do not
    select Linux or assert that every gnulib replacement works: the package's
    real target build and consumer tests still have to establish that.
    """
    stubs = set(metadata['stub_functions'])
    require(all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in stubs),
            'invalid SDK stub spelling')
    if 'libc_sigaction' in stubs:
        stubs.add('sigaction')
        # GNU libc deliberately omits the sigprocmask stub warning because
        # abort references it.  On this no-signal backend it still fails.
        stubs.add('sigprocmask')
    return ''.join('ac_cv_func_' + name + '=no\n' for name in sorted(stubs))


def configuration(sdk, metadata, tools, work, extra_cppflags=()):
    """Use only one authenticated SDK and its exact bare-metal compiler tools."""
    sysroot = sdk / 'sysroot'
    lib = sysroot / 'usr/lib'
    tool_dir = work / 'tools'
    tool_dir.mkdir()
    for name, tool in tools.items():
        (tool_dir / name).symlink_to(tool['path'])
    flags = ['--sysroot=' + str(sysroot), '-B' + str(tool_dir) + '/',
             '-mno-red-zone', '-fno-pie', '-fno-pic', '-fno-stack-protector',
             '-ftls-model=local-exec']
    includes = ['-D__xos__=1', *extra_cppflags, '-nostdinc', '-isystem',
                str(sysroot / 'usr/include'), '-isystem', str(lib / 'compiler-include')]
    start = ('xos_start.o', 'crti.o', 'crtbegin.o', 'xos_start_c.o', 'xos_stdio_receiver.o')
    libraries = ['libc.a', 'libm.a', 'libxos_terminal.a', 'libgcc.a']
    if (lib / 'libgcc_eh.a').is_file():
        libraries.append('libgcc_eh.a')
    end = ('crtend.o', 'crtn.o')
    links = ['-T', str(sysroot / 'user.ld'), *(str(lib / name) for name in start),
             '-Wl,--start-group', *(str(lib / name) for name in libraries),
             '-Wl,--end-group', *(str(lib / name) for name in end)]
    env, removed = clean_build_environment(os.environ)
    for name in list(env):
        if name.startswith(('ac_cv_', 'gl_cv_', 'make_cv_')) or name in (
                'LIBS', 'CONFIG_SITE', 'MAKEFLAGS', 'MFLAGS', 'GNUMAKEFLAGS',
                'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR'):
            del env[name]
            removed.append(name)
    site = work / 'config.site'
    site.write_text(target_site(metadata))
    env.update(LC_ALL='C', CC=shlex.join([tools['gcc']['path'], *flags]),
               AR=tools['ar']['path'], RANLIB=tools['ranlib']['path'],
               CFLAGS='-O2 -g -ffunction-sections -fdata-sections',
               CPPFLAGS=shlex.join(includes),
               LDFLAGS='-nostdlib -static -no-pie -Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096',
               LIBS=shlex.join(links), CONFIG_SITE=str(site),
               PKG_CONFIG_PATH='', PKG_CONFIG_LIBDIR=os.devnull)
    return env, sorted(set(removed))
