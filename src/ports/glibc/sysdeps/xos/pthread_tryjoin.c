/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <errno.h>
#include <shlib-compat.h>
#include "xos_thread_identity.h"
#include "xos_thread_extensions.h"

int
__pthread_tryjoin_np (pthread_t thread, void **value)
{
  struct xos_join_options options = { 1, sizeof (options), 0, 0, 1 };
  unsigned long result;
  long status = xos_thread_extension_call (44, (unsigned long) thread,
                                          (unsigned long) &result,
                                          (unsigned long) &options);
  if (status != 0)
    return xos_thread_lifecycle_error (status);
  if (value != NULL) *value = (void *) result;
  return 0;
}
versioned_symbol (libc, __pthread_tryjoin_np, pthread_tryjoin_np, GLIBC_2_34);
