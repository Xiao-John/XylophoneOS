/* SPDX-License-Identifier: Apache-2.0
   NPTL's stdio lock macros use EBUSY; include its declaration explicitly. */
#ifndef XOS_GLIBC_STDIO_LOCK_H
#define XOS_GLIBC_STDIO_LOCK_H 1
#include <errno.h>
#include_next <stdio-lock.h>
#endif
