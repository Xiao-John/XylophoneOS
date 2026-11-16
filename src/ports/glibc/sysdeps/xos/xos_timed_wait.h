/* SPDX-License-Identifier: Apache-2.0
   Private XOS monotonic absolute-wait conversion. */
#ifndef XOS_GLIBC_TIMED_WAIT_H
#define XOS_GLIBC_TIMED_WAIT_H 1
#include "xos_wait_word.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Returns a positive errno or zero; never changes errno.  This interface does
   not implement cancellation, process sharing or realtime clock semantics. */
__attribute__ ((visibility ("hidden")))
int __xos_wait_monotonic (xos_u32 *word, xos_u32 expected, int has_deadline,
                          xos_i64 seconds, long nanoseconds);
#ifdef __cplusplus
}
#endif
#endif
