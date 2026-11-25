/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
_Static_assert (sizeof (struct dirent) == sizeof (struct dirent64), "LP64 dirent layout");
struct dirent64 *__readdir64 (DIR *directory)
{
  struct dirent *entry = NULL;
  (void) xos_file_result (__xos_directory_read (directory, &entry));
  return (struct dirent64 *) entry;
}
libc_hidden_def (__readdir64)
weak_alias (__readdir64, readdir64)
