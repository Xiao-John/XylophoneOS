/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include "xos_file_result.h"
int __openat (int fd, const char *path, int flags, ...)
{
  if (path == 0) return (int) xos_file_result (-EFAULT);
  if (fd != AT_FDCWD && path[0] != '/') return (int) xos_file_result (-ENOTSUP);
  return (int) xos_file_result (__xos_file_open (path, flags));
}
libc_hidden_def (__openat)
weak_alias (__openat, openat)
