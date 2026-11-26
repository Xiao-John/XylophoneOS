/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_SYSDEP_CANCEL_H
#define XOS_GLIBC_SYSDEP_CANCEL_H 1

/* Reuse the XOS locking policy from sysdep.h.  The upstream generic
   sysdep-cancel.h assumes there are no threads and overrides that policy. */
#include <sysdep.h>

#endif
