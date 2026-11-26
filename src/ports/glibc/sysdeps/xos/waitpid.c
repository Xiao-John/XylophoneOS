/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <sys/wait.h>

extern long __xos_wait_child (pid_t, int *, int)
  __attribute__ ((visibility ("hidden")));

pid_t
__waitpid (pid_t pid, int *status, int options)
{
  long result = __xos_wait_child (pid, status, options);
  if (result < 0)
    {
      __set_errno ((int) -result);
      return -1;
    }
  return (pid_t) result;
}
libc_hidden_def (__waitpid)
weak_alias (__waitpid, waitpid)
