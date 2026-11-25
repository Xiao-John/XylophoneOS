/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>

int
__getpagesize (void)
{
  /* XOS's public mapping and startup ABI fixes the base page at 4 KiB. */
  return 4096;
}
libc_hidden_def (__getpagesize)
weak_alias (__getpagesize, getpagesize)
