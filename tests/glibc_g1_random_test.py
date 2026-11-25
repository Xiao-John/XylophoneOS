#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check XOS random request boundaries and explicit error translation."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='xos_glibc_random_') as folder:
    tmp = Path(folder)
    (tmp/'sys').mkdir()
    (tmp/'sys/random.h').write_text('''#include <stddef.h>
typedef long ssize_t;
#define GRND_NONBLOCK 1
#define GRND_RANDOM 2
#define GRND_INSECURE 4
#define __set_errno(x) (errno=(x))
#define libc_hidden_def(x)
#define weak_alias(a,b)
ssize_t __getrandom(void *, size_t, unsigned int);
int getentropy(void *, size_t);
''')
    exe = tmp/'test'
    subprocess.run(['clang', '-std=c11', '-Wall', '-Werror', '-DXOS_GLIBC_RANDOM_TEST', '-I', str(tmp),
                    str(root/'src/ports/glibc/sysdeps/xos/getrandom.c'),
                    str(root/'src/ports/glibc/sysdeps/xos/getentropy.c'),
                    str(root/'tests/fixtures/glibc_g1/random_test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
    (tmp/'errno.h').write_text('extern int errno;\n#define EINVAL 22\n#define ENOTSUP 134\n#define EFAULT 14\n#define ENOSYS 88\n#define EIO 5\n')
    obj = tmp/'target.o'
    subprocess.run(['x86_64-elf-gcc', '-std=c11', '-O2', '-ffreestanding', '-Wall', '-Werror',
                    '-I', str(tmp), '-c', str(root/'src/ports/glibc/sysdeps/xos/getrandom.c'), '-o', str(obj)], check=True)
    code = subprocess.check_output(['x86_64-elf-objdump', '-dr', str(obj)], text=True)
    assert '$0x3f,%eax' in code and 'int    $0x80' in code and '\tsyscall' not in code
print('PASS random limits, short reads, flags and errors')
