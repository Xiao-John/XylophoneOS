/* SPDX-License-Identifier: Apache-2.0 */
#include <limits.h>
#include <stdio.h>
#include <unistd.h>

void
__closefrom (int lowfd)
{
  if (__close_range (lowfd < 0 ? 0U : (unsigned int) lowfd, UINT_MAX, 0) != 0)
    __fortify_fail ("closefrom failed to close a file descriptor");
}
weak_alias (__closefrom, closefrom)
