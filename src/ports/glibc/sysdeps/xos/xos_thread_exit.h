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
#if defined SHARED && defined XOS_ONLINE_CLOSURE
/* DTV was captured while this worker still had usable TLS.  The elected
   last thread keeps it for process callbacks; other workers only publish it. */
__attribute__ ((noreturn, visibility ("hidden")))
void __xos_thread_finish_worker (unsigned long, void (*) (void), int, void *);
#endif
__attribute__ ((visibility ("hidden")))
void __xos_nptl_cleanup_current (void);
__attribute__ ((noreturn, visibility ("hidden")))
void __xos_nptl_last_process_exit (void);
__attribute__ ((noreturn, visibility ("hidden")))
void __xos_internal_exit (int status);
#ifdef __cplusplus
}
#endif
#endif
