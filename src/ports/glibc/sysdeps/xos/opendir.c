/* SPDX-License-Identifier: Apache-2.0 */
#include <dirent.h>
#include <fcntl.h>
#include "xos_file_directory.h"
#include "xos_file_result.h"

DIR *
__opendirat (int dfd, const char *name, int extra_flags, int *new_fd)
{
  if (name == NULL) { __set_errno (EFAULT); return NULL; }
  if (dfd != AT_FDCWD && name[0] != '/') { __set_errno (ENOTSUP); return NULL; }
  if ((extra_flags & ~(O_NOFOLLOW | O_NONBLOCK)) != 0)
    { __set_errno (EINVAL); return NULL; }
  long fd = __xos_file_open (name, O_RDONLY | O_DIRECTORY | O_CLOEXEC | extra_flags);
  if (fd < 0) { (void) xos_file_result (fd); return NULL; }
  DIR *directory = NULL;
  long result = __xos_directory_open ((int) fd, &directory);
  if (result < 0)
    {
      (void) __xos_file_close ((int) fd);
      (void) xos_file_result (result);
      return NULL;
    }
  if (new_fd != NULL) *new_fd = (int) fd;
  return directory;
}

DIR *__opendir (const char *name) { return __opendirat (AT_FDCWD, name, 0, NULL); }
weak_alias (__opendir, opendir)
