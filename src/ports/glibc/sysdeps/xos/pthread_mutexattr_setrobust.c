/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_mutexattr_setrobust (pthread_mutexattr_t *attribute, int robust)
{
  if (robust != PTHREAD_MUTEX_STALLED)
    return robust == PTHREAD_MUTEX_ROBUST ? ENOTSUP : EINVAL;
  ((struct pthread_mutexattr *) attribute)->mutexkind
    &= ~PTHREAD_MUTEXATTR_FLAG_ROBUST;
  return 0;
}
versioned_symbol (libc, __pthread_mutexattr_setrobust,
                  pthread_mutexattr_setrobust, GLIBC_2_34);
