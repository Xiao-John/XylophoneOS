/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

int
__chdir (const char *path)
{
  return (int) xos_file_result (__xos_file_chdir (path));
}
weak_alias (__chdir, chdir)
