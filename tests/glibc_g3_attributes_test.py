#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise XOS attributes using internal types from the locked glibc source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    overlay = root / 'src/ports/glibc/sysdeps/xos'
    lock = json.loads((root / 'src/ports/glibc/source_lock.json').read_text())
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != lock['archive_sha256']:
        raise SystemExit('glibc archive hash mismatch')
    with tarfile.open(args.archive) as archive:
        def read(name):
            stream = archive.extractfile(f"glibc-{lock['version']}/{name}")
            if stream is None:
                raise SystemExit(f'archive member missing: {name}')
            return stream.read().decode()
        types = read('sysdeps/nptl/internaltypes.h')
        private = read('sysdeps/nptl/pthreadP.h')
    # Copy exact upstream declarations; this host check does not qualify the
    # candidate public headers or ABI. The full target build/guest covers those.
    declarations = []
    for name in ('pthread_attr', 'pthread_mutexattr', 'pthread_condattr',
                 'pthread_rwlockattr', 'pthread_barrierattr'):
        match = re.search(r'struct ' + name + r'\n\{.*?\n\};', types, re.S)
        if match is None:
            raise SystemExit(f'upstream type missing: {name}')
        declarations.append(match.group())
    for name in ('ATTR_FLAG_DETACHSTATE', 'ATTR_FLAG_STACKADDR'):
        declarations.append(re.search(r'^#define ' + name + r'\s+\S+', types, re.M).group())
    for name in ('PTHREAD_MUTEXATTR_PROTOCOL_MASK', 'PTHREAD_MUTEXATTR_FLAG_ROBUST',
                 'PTHREAD_MUTEXATTR_FLAG_PSHARED'):
        declarations.append(re.search(r'^#define ' + name + r'\s+\S+', private, re.M).group())
    with tempfile.TemporaryDirectory(prefix='xos_glibc_g3_attr_') as directory:
        temporary = Path(directory)
        (temporary / 'pthreadP.h').write_text('''#pragma once
#include <pthread.h>
#include <stddef.h>
#include <string.h>
#define libc_hidden_def(name)
#define weak_alias(a,b)
pthread_t __pthread_self (void);
int __pthread_attr_init (pthread_attr_t *);
''' + '\n'.join(declarations) + '''
union pthread_attr_transparent { pthread_attr_t external; struct pthread_attr internal; };
''')
        (temporary / 'shlib-compat.h').write_text('#define versioned_symbol(a,b,c,d)\n')
        (temporary / 'lowlevellock.h').write_text('''#include <assert.h>
#define LLL_PRIVATE 0
#define lll_lock(word, kind) assert (__atomic_exchange_n (&(word), 1, __ATOMIC_ACQUIRE) == 0)
#define lll_unlock(word, kind) assert (__atomic_exchange_n (&(word), 0, __ATOMIC_RELEASE) == 1)
''')
        sources = ['pthread_mutexattr_setpshared', 'pthread_condattr_setpshared',
                   'pthread_rwlockattr_setpshared', 'pthread_barrierattr_setpshared',
                   'pthread_mutexattr_setrobust', 'pthread_mutexattr_setprotocol',
                   'pthread_setcanceltype', 'pthread_gettid_np', 'pthread_getattr_np',
                   'xos_thread_name']
        command = [os.environ.get('CC', 'cc'), '-std=c11', '-D_GNU_SOURCE', '-O2', '-g',
                   '-Wall', '-Wextra', '-Werror', '-DXOS_GLIBC_IDENTITY_TEST',
                   '-I', str(temporary), '-I', str(overlay)]
        if args.sanitize:
            command += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        command += [str(overlay / (source + '.c')) for source in sources]
        executable = temporary / 'attributes'
        command += [str(root / 'tests/fixtures/glibc_g3/attributes.c'), '-o', str(executable)]
        subprocess.run(command, check=True)
        environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1')
        subprocess.run([str(executable)], env=environment, check=True, timeout=20)
    print('PASS G3 attributes: shared/robust/PI/async rejection, exact output '
          'preservation, live/stale/64-bit TIDs, current stack, detach snapshot')


if __name__ == '__main__':
    main()
