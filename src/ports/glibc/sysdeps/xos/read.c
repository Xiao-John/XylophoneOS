/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
ssize_t __libc_read (int fd, void *buffer, size_t length)
{ return xos_file_result (__xos_file_read (fd, buffer, length)); }
libc_hidden_def (__libc_read)
weak_alias (__libc_read, __read)
libc_hidden_weak (__read)
weak_alias (__libc_read, read)
libc_hidden_weak (read)
