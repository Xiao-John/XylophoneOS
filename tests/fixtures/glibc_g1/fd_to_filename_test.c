/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stddef.h>
#include "fd_to_filename.h"
int main (void)
{
  struct fd_to_filename storage = {0};
  errno = 0;
  if (__fd_to_filename (3, &storage) != NULL || errno != ENOTSUP) return 1;
  errno = 0;
  if (__fd_to_filename (-1, &storage) != NULL || errno != ENOTSUP) return 2;
  return 0;
}
