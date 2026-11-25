/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <shlib-compat.h>
#include "xos_thread_identity.h"

int
___pthread_detach (pthread_t thread)
{
  xos_i64 error = xos_thread_lifecycle (45, (xos_u64) thread, 0);
  return error == 0 ? 0 : xos_thread_lifecycle_error (error);
}
versioned_symbol (libc, ___pthread_detach, pthread_detach, GLIBC_2_34);
libc_hidden_ver (___pthread_detach, __pthread_detach)
#ifndef SHARED
strong_alias (___pthread_detach, __pthread_detach)
#endif
