/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include <errno.h>
int __readdir64_r (DIR *directory, struct dirent64 *entry, struct dirent64 **result)
{
  if (result == NULL) return EINVAL;
  struct dirent *current = NULL;
  long status = __xos_directory_read_copy (directory, (struct dirent *) entry, &current);
  *result = (struct dirent64 *) current;
  return status < 0 ? (int) -status : 0;
}
weak_alias (__readdir64_r, readdir64_r)
