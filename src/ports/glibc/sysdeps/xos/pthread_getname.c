/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>
#include "xos_thread_name.h"

int
__pthread_getname_np (pthread_t thread, char *name, size_t size)
{
  if (size < XOS_THREAD_NAME_SIZE)
    return ERANGE;
  return __xos_thread_name_get ((xos_u64) thread, name);
}
versioned_symbol (libc, __pthread_getname_np, pthread_getname_np, GLIBC_2_34);
