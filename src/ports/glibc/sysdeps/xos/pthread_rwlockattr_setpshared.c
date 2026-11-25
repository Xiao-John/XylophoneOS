/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_rwlockattr_setpshared (pthread_rwlockattr_t *attribute, int shared)
{
  if (shared != PTHREAD_PROCESS_PRIVATE)
    return shared == PTHREAD_PROCESS_SHARED ? ENOTSUP : EINVAL;
  ((struct pthread_rwlockattr *) attribute)->pshared = PTHREAD_PROCESS_PRIVATE;
  return 0;
}
versioned_symbol (libc, __pthread_rwlockattr_setpshared,
                  pthread_rwlockattr_setpshared, GLIBC_2_34);
