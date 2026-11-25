/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <time.h>
#include "xos_thread_identity.h"

int
__pthread_clockjoin_ex (pthread_t thread, void **value, clockid_t clockid,
                        const struct __timespec64 *deadline, bool cancel)
{
  if (deadline != NULL)
    {
      if ((clockid != CLOCK_MONOTONIC && clockid != CLOCK_REALTIME)
          || !valid_nanoseconds (deadline->tv_nsec))
        return EINVAL;
      return ENOTSUP;
    }

  if (cancel)
    __pthread_testcancel ();
  /* The kernel pins this slot until it can deliver the result. It must be
     writable and aligned even for a caller that discards the result. */
  xos_u64 result;
  xos_i64 error = xos_thread_lifecycle (44, (xos_u64) thread, (xos_u64) &result);
  if (error != 0)
    return xos_thread_lifecycle_error (error);
  if (value != NULL)
    *value = (void *) result;
  return 0;
}
