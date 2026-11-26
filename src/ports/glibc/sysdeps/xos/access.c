/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

int
__access (const char *path, int mode)
{
  return (int) xos_file_result (__xos_file_access (path, mode));
}
libc_hidden_def (__access)
weak_alias (__access, access)
