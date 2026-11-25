/* SPDX-License-Identifier: Apache-2.0
   XOS integration of glibc's private, untimed low-level wait and wake.  */
#ifndef XOS_GLIBC_LOWLEVELLOCK_FUTEX_H
#define XOS_GLIBC_LOWLEVELLOCK_FUTEX_H 1
#include_next <lowlevellock-futex.h>
#ifndef __ASSEMBLER__
# include <xos_lll_futex.h>
/* This low-level entry is for untimed waits. Absolute monotonic/realtime
   deadlines use futex-internal.c; relative times and shared keys must not
   be silently treated as private, untimed operations. */
# undef lll_futex_timed_wait
# define lll_futex_timed_wait(word, expected, timeout, private) \
  ({ __auto_type __xos_timeout = (timeout); \
     int __xos_private = (private); \
     if (__xos_private != LLL_PRIVATE || __xos_timeout != 0) __builtin_trap (); \
     __xos_lll_wait ((unsigned int *) (word), (expected)); })
# undef lll_futex_wake
# define lll_futex_wake(word, count, private) \
  ({ int __xos_private = (private); \
     if (__xos_private != LLL_PRIVATE) __builtin_trap (); \
     __xos_lll_wake ((unsigned int *) (word), (count)); })
/* Remaining Linux futex operations have no XOS implementation.  Trap rather
   than silently dropping an operation or passing Linux numbers to XOS.  */
# undef lll_futex_requeue
# define lll_futex_requeue(...) (__builtin_trap (), 0)
# undef lll_futex_wake_unlock
# define lll_futex_wake_unlock(...) (__builtin_trap (), 0)
# undef lll_futex_timed_unlock_pi
# define lll_futex_timed_unlock_pi(...) (__builtin_trap (), 0)
# undef lll_futex_cmp_requeue_pi
# define lll_futex_cmp_requeue_pi(...) (__builtin_trap (), 0)
# undef lll_futex_wait_cancel
# define lll_futex_wait_cancel(...) (__builtin_trap (), 0)
# undef lll_futex_supported_clockid
# define lll_futex_supported_clockid(clockid) \
  ({ int __xos_clock = (clockid); \
     __xos_clock == CLOCK_MONOTONIC || __xos_clock == CLOCK_REALTIME; })
#endif
#endif
