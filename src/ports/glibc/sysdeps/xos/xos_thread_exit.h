/* SPDX-License-Identifier: Apache-2.0
   XOS thread termination primitive for the experimental glibc port. */
#ifndef XOS_GLIBC_THREAD_EXIT_H
#define XOS_GLIBC_THREAD_EXIT_H 1
#ifdef __cplusplus
extern "C" {
#endif
/* Call after all thread-local cleanup. The elected last thread runs
   LAST_PROCESS_EXIT with its TLS intact. That callback must not return. */
__attribute__ ((noreturn, visibility ("hidden")))
void __xos_thread_finish (unsigned long result, void (*last_process_exit) (void));
__attribute__ ((noreturn, visibility ("hidden")))
void __xos_internal_exit (int status);
#ifdef __cplusplus
}
#endif
#endif
