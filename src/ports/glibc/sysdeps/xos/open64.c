/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include "xos_file_result.h"
int __libc_open64 (const char *path, int flags, ...)
{ return (int) xos_file_result (__xos_file_open (path, flags)); }
strong_alias (__libc_open64, __open64)
libc_hidden_def (__open64)
weak_alias (__libc_open64, open64)
