#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the G1 native pthread attribute query reports an unsupported operation."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'src/ports/glibc/sysdeps/xos/pthread_getattr_np.c'
with tempfile.TemporaryDirectory(prefix='xos_glibc_g1_getattr_') as temporary:
    temporary = Path(temporary)
    (temporary / 'shlib-compat.h').write_text('#define versioned_symbol(a,b,c,d)\n')
    probe = temporary / 'probe.c'
    probe.write_text(r"""
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <string.h>
int __pthread_getattr_np (pthread_t, pthread_attr_t *);
int main (void)
{
  pthread_attr_t attribute;
  unsigned char before[sizeof attribute];
  memset (&attribute, 0xa5, sizeof attribute);
  memcpy (before, &attribute, sizeof before);
  errno = EBUSY;
  assert (__pthread_getattr_np ((pthread_t) 42, &attribute) == ENOTSUP);
  assert (memcmp (before, &attribute, sizeof before) == 0);
  assert (errno == EBUSY);
  return 0;
}
""")
    executable = temporary / 'probe'
    subprocess.run([os.environ.get('CC', 'clang'), '-std=c11', '-Wall', '-Werror',
                    '-I', temporary, source, probe, '-o', executable], check=True)
    subprocess.run([executable], check=True)
print('PASS G1 pthread attribute query preserves output and errno')
