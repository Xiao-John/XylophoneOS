/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_POSITIONED_H
#define XOS_GLIBC_FILE_POSITIONED_H 1
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
long __xos_file_pread (int, void *, size_t, long) __attribute__ ((visibility ("hidden")));
long __xos_file_pwrite (int, const void *, size_t, long) __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
