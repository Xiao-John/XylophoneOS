/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>
#include <string.h>
#include "xos_thread_name.h"

int
__pthread_setname_np (pthread_t thread, const char *name)
{
  size_t length = __strnlen (name, XOS_THREAD_NAME_SIZE);
  if (length == XOS_THREAD_NAME_SIZE)
    return ERANGE;
  return __xos_thread_name_set ((xos_u64) thread, name, length);
}
versioned_symbol (libc, __pthread_setname_np, pthread_setname_np, GLIBC_2_34);
