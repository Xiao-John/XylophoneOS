/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>

int
__pthread_mutexattr_setprotocol (pthread_mutexattr_t *attribute, int protocol)
{
  if (protocol != PTHREAD_PRIO_NONE)
    return (protocol == PTHREAD_PRIO_INHERIT || protocol == PTHREAD_PRIO_PROTECT)
      ? ENOTSUP : EINVAL;
  ((struct pthread_mutexattr *) attribute)->mutexkind
    &= ~PTHREAD_MUTEXATTR_PROTOCOL_MASK;
  return 0;
}
versioned_symbol (libc, __pthread_mutexattr_setprotocol,
                  pthread_mutexattr_setprotocol, GLIBC_2_34);
