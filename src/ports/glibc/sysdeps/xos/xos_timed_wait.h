/* SPDX-License-Identifier: Apache-2.0
   Private XOS absolute-wait conversion. */
#ifndef XOS_GLIBC_TIMED_WAIT_H
#define XOS_GLIBC_TIMED_WAIT_H 1
#include "xos_wait_word.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Returns a positive errno or zero; never changes errno. Private waits use
   the native monotonic domain. Realtime deadlines use the fixed boot-RTC
   offset and are rechecked after timeout to exclude sampling skew. */
__attribute__ ((visibility ("hidden")))
int __xos_wait_monotonic (xos_u32 *word, xos_u32 expected, int has_deadline,
                          xos_i64 seconds, long nanoseconds);
__attribute__ ((visibility ("hidden")))
int __xos_wait_realtime (xos_u32 *word, xos_u32 expected, int has_deadline,
                       xos_i64 seconds, long nanoseconds);
#ifdef __cplusplus
}
#endif
#endif
