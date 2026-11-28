/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_SLEEP_H
#define XOS_GLIBC_SLEEP_H 1
#include "xos_wait_word.h"

__attribute__ ((visibility ("hidden")))
int __xos_sleep_until (xos_u64, xos_u64 *);
__attribute__ ((visibility ("hidden")))
void __xos_sleep_after_fork (void);
#endif
