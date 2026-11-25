/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <shlib-compat.h>
#include "xos_thread_identity.h"
#include "xos_thread_name.h"

int
__pthread_getattr_np (pthread_t thread, pthread_attr_t *attribute)
{
  struct xos_thread_info self = { 0 };
  xos_i64 status = xos_thread_lifecycle (41, (xos_u64) &self, 0);
  if (status != 0)
    return xos_thread_lifecycle_error (status);
  struct xos_thread_attributes value;
  int error = __xos_thread_attributes_get (thread, self.stack_bottom,
                                           self.stack_top, &value);
  if (error != 0)
    return error;

  /* Construct a value only after the snapshot succeeds. Querying a stale
     handle preserves the caller's output and never touches freed TLS. */
  union pthread_attr_transparent result;
  error = __pthread_attr_init (&result.external);
  if (error != 0)
    return error;
  result.internal.stackaddr = (void *) value.stack_top;
  result.internal.stacksize = value.stack_top - value.stack_bottom;
  result.internal.guardsize = value.guard_size;
  result.internal.flags |= ATTR_FLAG_STACKADDR;
  if (value.detached)
    result.internal.flags |= ATTR_FLAG_DETACHSTATE;
  *attribute = result.external;
  return 0;
}
versioned_symbol (libc, __pthread_getattr_np, pthread_getattr_np, GLIBC_2_32);
