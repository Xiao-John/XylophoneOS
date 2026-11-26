/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include "xos_file_result.h"
/* The FAT service applies its documented fixed permission projection. */
int __libc_open (const char *path, int flags, ...)
{ return (int) xos_file_result (__xos_file_open (path, flags)); }
libc_hidden_def (__libc_open)
strong_alias (__libc_open, __open)
libc_hidden_def (__open)
weak_alias (__libc_open, open)
