/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_mutexattr_setpshared (pthread_mutexattr_t *attribute, int shared)
{
  if (shared != PTHREAD_PROCESS_PRIVATE)
    return shared == PTHREAD_PROCESS_SHARED ? ENOTSUP : EINVAL;
  ((struct pthread_mutexattr *) attribute)->mutexkind &= ~PTHREAD_MUTEXATTR_FLAG_PSHARED;
  return 0;
}
versioned_symbol (libc, __pthread_mutexattr_setpshared,
                  pthread_mutexattr_setpshared, GLIBC_2_34);
