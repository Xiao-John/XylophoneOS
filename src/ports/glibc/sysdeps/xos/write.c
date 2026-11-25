/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
ssize_t __libc_write (int fd, const void *buffer, size_t length)
{ return xos_file_result (__xos_file_write (fd, buffer, length)); }
libc_hidden_def (__libc_write)
weak_alias (__libc_write, __write)
libc_hidden_weak (__write)
weak_alias (__libc_write, write)
libc_hidden_weak (write)
