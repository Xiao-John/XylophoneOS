/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <sys/stat.h>
#include "xos_file_result.h"

/* The internal stat header declares __fstatat but only hides __fstatat64. */
libc_hidden_proto (__fstatat)

int __fstatat (int fd, const char *path, struct stat *output, int flags)
{
  if (path == 0) return (int) xos_file_result (-EFAULT);
  if ((flags & ~(AT_SYMLINK_NOFOLLOW | AT_EMPTY_PATH)) != 0)
    return (int) xos_file_result (-EINVAL);
  if (path[0] == 0 && (flags & AT_EMPTY_PATH))
    return (int) xos_file_result (__xos_file_stat (fd, 0, output));
  if (fd != AT_FDCWD && path[0] != '/') return (int) xos_file_result (-ENOTSUP);
  return (int) xos_file_result (__xos_file_stat (fd, path, output));
}
libc_hidden_def (__fstatat)
weak_alias (__fstatat, fstatat)
