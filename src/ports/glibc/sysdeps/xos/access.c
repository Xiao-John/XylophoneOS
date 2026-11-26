/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

extern long __xos_inspect_image (xos_image_read, void *, xos_u64)
  __attribute__ ((visibility ("hidden")));

int
__access (const char *path, int mode)
{
  return (int) xos_file_result (__xos_file_access (path, mode, __xos_inspect_image));
}
libc_hidden_def (__access)
weak_alias (__access, access)
