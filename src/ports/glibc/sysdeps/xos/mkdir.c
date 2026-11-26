/* SPDX-License-Identifier: Apache-2.0 */
#include <sys/stat.h>
#include "xos_file_result.h"

int
__mkdir (const char *path, mode_t mode)
{
  /* FAT does not store POSIX permission bits. */
  (void) mode;
  return (int) xos_file_result (__xos_file_path_op (path, 15));
}
libc_hidden_def (__mkdir)
weak_alias (__mkdir, mkdir)
