/* SPDX-License-Identifier: Apache-2.0 */
#include <dirent.h>
#include <errno.h>
#include "dirstream.h"
int __dirfd (DIR *directory)
{
  if (directory == NULL) { __set_errno (EINVAL); return -1; }
  return directory->fd;
}
weak_alias (__dirfd, dirfd)
libc_hidden_def (dirfd)
