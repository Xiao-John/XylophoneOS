/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_positioned.h"
#include "xos_file_result.h"
ssize_t __libc_pread (int fd, void *buffer, size_t length, off_t offset)
{ return xos_file_result (__xos_file_pread (fd, buffer, length, offset)); }
strong_alias (__libc_pread, __pread)
libc_hidden_def (__pread)
weak_alias (__libc_pread, pread)
