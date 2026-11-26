/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

int
__rmdir (const char *path)
{
  return (int) xos_file_result (__xos_file_path_op (path, 32));
}
weak_alias (__rmdir, rmdir)
