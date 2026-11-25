/* SPDX-License-Identifier: Apache-2.0
   Experimental XOS implementations of glibc's internal timed waits. */
#include <atomic.h>
#include <errno.h>
#include <time.h>
#include <futex-internal.h>
#include <xos_timed_wait.h>

int
__futex_abstimed_wait64 (unsigned int *word, unsigned int expected,
                          clockid_t clockid, const struct __timespec64 *abstime,
                          int private)
{
  /* Shared address-space keys do not exist in the XOS wait ABI.  Do not
     continue as though an independent process can wake this waiter. */
  if (private != FUTEX_PRIVATE)
    __builtin_trap ();
  if (clockid != CLOCK_MONOTONIC)
    return EINVAL;
  int result = __xos_wait_monotonic (word, expected, abstime != NULL,
                                      abstime ? abstime->tv_sec : 0,
                                      abstime ? abstime->tv_nsec : 0);
  switch (result)
    {
    case 0: case EAGAIN: case EINTR: case ETIMEDOUT:
    case EINVAL: case EOVERFLOW:
      return result;
    default:
      /* Match glibc's contract for unexpected kernel or resource errors;
         returning one that callers ignore can cause an infinite loop. */
      futex_fatal_error ();
    }
}
libc_hidden_def (__futex_abstimed_wait64)

int
__futex_abstimed_wait_cancelable64 (unsigned int *word, unsigned int expected,
                                     clockid_t clockid,
                                     const struct __timespec64 *abstime,
                                     int private)
{
  (void) word; (void) expected; (void) clockid; (void) abstime; (void) private;
  /* Cancellation cannot be silently disabled around a blocking call. */
  __builtin_trap ();
}
libc_hidden_def (__futex_abstimed_wait_cancelable64)

int
__futex_lock_pi64 (int *word, clockid_t clockid,
                   const struct __timespec64 *abstime, int private)
{
  (void) word; (void) clockid; (void) abstime; (void) private;
  /* Some NPTL PI callers ignore errors outside their expected set and would
     proceed as though a lock were acquired.  Fail closed until supported. */
  __builtin_trap ();
}
