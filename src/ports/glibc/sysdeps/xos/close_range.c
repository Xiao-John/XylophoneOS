/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

int
__close_range (unsigned int first, unsigned int last, int flags)
{
  if (flags != 0) return (int) xos_file_result (-EINVAL);
  return (int) xos_file_result (__xos_file_close_range (first, last));
}
libc_hidden_def (__close_range)
weak_alias (__close_range, close_range)
