/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <sys/stat.h>
#include <string.h>
#include "xos_file_result.h"
int __fstatat64 (int fd, const char *path, struct stat64 *output, int flags)
{
  if (path == 0 || output == 0) return (int) xos_file_result (-EFAULT);
  /* The generic statx forwards AT_NO_AUTOMOUNT. XOS has no automounts. */
  if ((flags & ~(AT_SYMLINK_NOFOLLOW | AT_NO_AUTOMOUNT | AT_EMPTY_PATH)) != 0)
    return (int) xos_file_result (-EINVAL);
  const char *effective = path[0] == 0 && (flags & AT_EMPTY_PATH) ? 0 : path;
  if (effective != 0 && fd != AT_FDCWD && path[0] != '/')
    return (int) xos_file_result (-ENOTSUP);
  struct stat value;
  long result = __xos_file_stat (fd, effective, &value);
  if (result != 0) return (int) xos_file_result (result);
  memset (output, 0, sizeof (*output));
  output->st_mode = value.st_mode; output->st_ino = value.st_ino;
  output->st_dev = value.st_dev; output->st_nlink = value.st_nlink;
  output->st_uid = value.st_uid; output->st_gid = value.st_gid;
  output->st_size = value.st_size;
  output->st_atime = value.st_atime; output->st_mtime = value.st_mtime;
  output->st_ctime = value.st_ctime;
  output->st_atim.tv_nsec = value.st_atim.tv_nsec;
  output->st_mtim.tv_nsec = value.st_mtim.tv_nsec;
  output->st_ctim.tv_nsec = value.st_ctim.tv_nsec;
  output->st_rdev = value.st_rdev; output->st_blksize = value.st_blksize;
  output->st_blocks = value.st_blocks;
  return 0;
}
hidden_def (__fstatat64)
weak_alias (__fstatat64, fstatat64)
