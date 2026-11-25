/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
int __readdir_r (DIR *directory, struct dirent *entry, struct dirent **result)
{
  long status = __xos_directory_read_copy (directory, entry, result);
  return status < 0 ? (int) -status : 0;
}
weak_alias (__readdir_r, readdir_r)
