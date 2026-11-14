/* SPDX-License-Identifier: Apache-2.0
   Private glibc TLS setup in an XOS-owned thread reservation. */
#ifndef XOS_GLIBC_THREAD_TLS_H
#define XOS_GLIBC_THREAD_TLS_H 1
#include "xos_thread_create.h"
struct pthread;
/* 0 on success, -1 for an unsuitable region, -2 for DTV allocation failure.
   Output is modified only on success.  The caller still owns the reserved
   region and must complete all other pthread initialization before start. */
__attribute__ ((visibility ("hidden")))
int __xos_thread_tls_initialize (const struct xos_thread_reservation *,
                                 struct pthread **);
/* Only for a successfully initialized TLS before start.  Invoke exactly once
   before aborting the reservation.  Normal thread-exit reclamation is not yet
   implemented: the kernel can unmap TLS before a joiner can inspect it. */
__attribute__ ((visibility ("hidden")))
void __xos_thread_tls_release (struct pthread *);
#endif
