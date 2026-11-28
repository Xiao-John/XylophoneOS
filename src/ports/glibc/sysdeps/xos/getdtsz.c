/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_limits.h"

int
__getdtablesize (void)
{
  return xos_file_descriptor_limit;
}
weak_alias (__getdtablesize, getdtablesize)
