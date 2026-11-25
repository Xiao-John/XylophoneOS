/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
long __internal_syscall_cancel (long, long, long, long, long, long, long);
long __syscall_cancel (long, long, long, long, long, long, long);
int main (void)
{
  errno = EINVAL;
  if (__internal_syscall_cancel (1, 2, 3, 4, 5, 6, 7) != -ENOSYS || errno != EINVAL) return 1;
  errno = 0;
  if (__syscall_cancel (1, 2, 3, 4, 5, 6, 7) != -1 || errno != ENOSYS) return 2;
  return 0;
}
