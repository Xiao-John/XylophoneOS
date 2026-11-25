/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_THREAD_NAME_H
#define XOS_GLIBC_THREAD_NAME_H 1

#include "xos_thread_create.h"

enum { XOS_THREAD_NAME_SIZE = 16 };
__attribute__ ((visibility ("hidden")))
int __xos_thread_name_add (xos_u64 tid);
__attribute__ ((visibility ("hidden")))
void __xos_thread_name_remove (xos_u64 tid);
__attribute__ ((visibility ("hidden")))
int __xos_thread_name_get (xos_u64 tid, char *output);
__attribute__ ((visibility ("hidden")))
int __xos_thread_name_set (xos_u64 tid, const char *name, unsigned long length);

#endif
