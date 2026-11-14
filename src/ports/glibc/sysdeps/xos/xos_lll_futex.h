/* SPDX-License-Identifier: Apache-2.0
   Provisional adapter for glibc's private untimed low-level waits. */
#ifndef XOS_GLIBC_LLL_FUTEX_H
#define XOS_GLIBC_LLL_FUTEX_H 1
#ifdef __cplusplus
extern "C" {
#endif
__attribute__ ((visibility ("hidden")))
int __xos_lll_wait (unsigned int *word, unsigned int expected);
__attribute__ ((visibility ("hidden")))
int __xos_lll_wake (unsigned int *word, int count);
#ifdef __cplusplus
}
#endif
#endif
