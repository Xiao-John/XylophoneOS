/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
struct dirent *__readdir (DIR *directory)
{
  struct dirent *entry = NULL;
  (void) xos_file_result (__xos_directory_read (directory, &entry));
  return entry;
}
strong_alias (__readdir, __readdir_unlocked)
weak_alias (__readdir, readdir)
