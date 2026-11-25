/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
DIR *__fdopendir (int fd)
{
  DIR *directory = NULL;
  (void) xos_file_result (__xos_directory_open (fd, &directory));
  return directory;
}
weak_alias (__fdopendir, fdopendir)
