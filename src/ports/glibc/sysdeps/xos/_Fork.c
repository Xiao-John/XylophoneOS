/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <unistd.h>
pid_t
_Fork (void)
{
  __set_errno (ENOSYS);
  return -1;
}
libc_hidden_def (_Fork)
stub_warning (_Fork)
