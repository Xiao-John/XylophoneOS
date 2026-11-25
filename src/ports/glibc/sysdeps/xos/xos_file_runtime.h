/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_RUNTIME_H
#define XOS_GLIBC_FILE_RUNTIME_H 1
#include "xos_file_wire.h"
#include <stddef.h>
#include <sys/stat.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Return a nonnegative result or negative libc errno, without touching TLS. */
long __xos_file_open (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_close (int) __attribute__ ((visibility ("hidden")));
long __xos_file_read (int, void *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_write (int, const void *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_seek (int, long, int) __attribute__ ((visibility ("hidden")));
long __xos_file_stat (int, const char *, struct stat *) __attribute__ ((visibility ("hidden")));
long __xos_file_dup (int, int, int, int) __attribute__ ((visibility ("hidden")));
long __xos_file_fcntl (int, int, int) __attribute__ ((visibility ("hidden")));
long __xos_file_path_op (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_truncate (int, long) __attribute__ ((visibility ("hidden")));
long __xos_file_sync (int) __attribute__ ((visibility ("hidden")));
long __xos_file_isatty (int) __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
