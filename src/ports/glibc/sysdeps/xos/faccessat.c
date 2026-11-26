/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <unistd.h>
#include "xos_file_result.h"

int
__faccessat (int fd, const char *path, int mode, int flags)
{
  if (path == 0) return (int) xos_file_result (-EFAULT);
  if ((flags & ~(AT_EACCESS | AT_SYMLINK_NOFOLLOW)) != 0
      || (mode & ~(R_OK | W_OK | X_OK)) != 0)
    return (int) xos_file_result (-EINVAL);
  if (path[0] != '/' && fd != AT_FDCWD)
    return (int) xos_file_result (fd < 0 ? -EBADF : -ENOTSUP);

  /* The file service authorizes the current session. Its namespace has
     no symbolic links or separate real and effective file identities. */
  return (int) xos_file_result (__xos_file_access (path, mode));
}
weak_alias (__faccessat, faccessat)
