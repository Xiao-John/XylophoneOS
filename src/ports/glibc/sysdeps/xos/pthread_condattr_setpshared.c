/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_condattr_setpshared (pthread_condattr_t *attribute, int shared)
{
  if (shared != PTHREAD_PROCESS_PRIVATE)
    return shared == PTHREAD_PROCESS_SHARED ? ENOTSUP : EINVAL;
  ((struct pthread_condattr *) attribute)->value &= ~1;
  return 0;
}
versioned_symbol (libc, __pthread_condattr_setpshared,
                  pthread_condattr_setpshared, GLIBC_2_34);
