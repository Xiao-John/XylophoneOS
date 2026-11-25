/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_positioned.h"
#include "xos_file_result.h"
ssize_t __libc_pread64 (int fd, void *buffer, size_t length, off64_t offset)
{ return xos_file_result (__xos_file_pread (fd, buffer, length, offset)); }
strong_alias (__libc_pread64, __pread64)
libc_hidden_def (__pread64)
weak_alias (__libc_pread64, pread64)
