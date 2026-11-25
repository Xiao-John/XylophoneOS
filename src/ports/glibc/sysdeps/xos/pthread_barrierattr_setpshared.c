/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_barrierattr_setpshared (pthread_barrierattr_t *attribute, int shared)
{
  if (shared != PTHREAD_PROCESS_PRIVATE)
    return shared == PTHREAD_PROCESS_SHARED ? ENOTSUP : EINVAL;
  ((struct pthread_barrierattr *) attribute)->pshared = PTHREAD_PROCESS_PRIVATE;
  return 0;
}
versioned_symbol (libc, __pthread_barrierattr_setpshared,
                  pthread_barrierattr_setpshared, GLIBC_2_34);
