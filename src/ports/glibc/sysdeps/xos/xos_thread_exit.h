/* SPDX-License-Identifier: Apache-2.0
   XOS thread termination primitive for the experimental glibc port. */
#ifndef XOS_GLIBC_THREAD_EXIT_H
#define XOS_GLIBC_THREAD_EXIT_H 1
#ifdef __cplusplus
extern "C" {
#endif
__attribute__ ((noreturn, visibility ("hidden")))
void __xos_internal_exit (int status);
#ifdef __cplusplus
}
#endif
#endif
