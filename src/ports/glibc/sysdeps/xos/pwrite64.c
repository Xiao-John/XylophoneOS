/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_positioned.h"
#include "xos_file_result.h"
ssize_t __libc_pwrite64 (int fd, const void *buffer, size_t length, off64_t offset)
{ return xos_file_result (__xos_file_pwrite (fd, buffer, length, offset)); }
strong_alias (__libc_pwrite64, __pwrite64)
libc_hidden_def (__pwrite64)
weak_alias (__libc_pwrite64, pwrite64)
