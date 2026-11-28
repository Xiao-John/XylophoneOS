/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <time.h>
#include "xos_thread_identity.h"
#include "xos_thread_extensions.h"
#if defined SHARED && defined XOS_ONLINE_CLOSURE
# include "xos_thread_tls.h"
#endif

int
__pthread_clockjoin_ex (pthread_t thread, void **value, clockid_t clockid,
                        const struct __timespec64 *deadline, bool cancel)
{
  struct xos_join_options options = { 1, sizeof (options), 0, 0, 2 };
  unsigned long absolute = 0;
  if (deadline != NULL)
    {
      if ((clockid != CLOCK_MONOTONIC && clockid != CLOCK_REALTIME)
          || !valid_nanoseconds (deadline->tv_nsec))
        return EINVAL;
      if (deadline->tv_sec >= 0 && (unsigned long) deadline->tv_sec
          > (ULONG_MAX - 1 - deadline->tv_nsec) / 1000000000UL)
        return EOVERFLOW;
      absolute = deadline->tv_sec < 0 ? 0
        : (unsigned long) deadline->tv_sec * 1000000000UL + deadline->tv_nsec;
    }

  if (cancel)
    __pthread_testcancel ();
  for (;;)
    {
      options.deadline_ns = absolute;
      if (deadline != NULL && clockid == CLOCK_REALTIME && absolute != 0)
        {
          /* Reading monotonic first makes preemption skew conservative.
             An early native timeout is rechecked against the original wall
             deadline, never converted into an early public timeout. */
          long mono = xos_thread_extension_call (46, 0, 0, 0);
          long wall = xos_thread_extension_call (64, 0, 0, 0);
          if (mono < 0) return EOVERFLOW;
          if (wall < 0) return EIO;
          if (absolute <= (unsigned long) wall) options.deadline_ns = 0;
          else
            {
              unsigned long remaining = absolute - (unsigned long) wall;
              if (remaining > ULONG_MAX - 1 - (unsigned long) mono)
                return EOVERFLOW;
              options.deadline_ns = (unsigned long) mono + remaining;
            }
        }
      /* The result slot stays pinned until completion or timeout. Even when
         the wall deadline has passed, the atomic join gets first refusal of
         an already completed result through its zero-deadline check. */
      xos_u64 result;
      xos_i64 error = deadline == NULL
        ? xos_thread_lifecycle (44, (xos_u64) thread, (xos_u64) &result)
        : xos_thread_extension_call (44, (xos_u64) thread, (xos_u64) &result,
                                     (xos_u64) &options);
      if (error == -13 && deadline != NULL && clockid == CLOCK_REALTIME
          && options.deadline_ns != 0)
        continue;
      if (error == -13) return ETIMEDOUT;
      if (error != 0) return xos_thread_lifecycle_error (error);
      if (value != NULL) *value = (void *) result;
#if defined SHARED && defined XOS_ONLINE_CLOSURE
      __xos_thread_tls_drain ();
#endif
      return 0;
    }
}
