/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_LIMITS_H
#define XOS_GLIBC_FILE_LIMITS_H 1

/* All libc routes (file, console, terminal, pipe and socket) use this table.
   This is a private libc capacity, not a new kernel or files-service ABI. */
enum { xos_file_descriptor_limit = 32, xos_file_object_limit = 32 };

#endif
