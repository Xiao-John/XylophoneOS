/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include "xos_file_result.h"

ssize_t
__readlink (const char *path, char *buffer, size_t length)
{
  (void) buffer;
  if (length == 0) return xos_file_result (-EINVAL);
  if (path == 0) return xos_file_result (-EFAULT);

  /* Resolve through the caller's file session so missing paths and
     directory traversal errors survive on a filesystem without links. */
  struct stat status;
  long result = __xos_file_stat (AT_FDCWD, path, &status);
  return xos_file_result (result == 0 ? -EINVAL : result);
}
weak_alias (__readlink, readlink)
