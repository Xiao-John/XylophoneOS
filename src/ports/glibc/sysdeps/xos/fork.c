/* SPDX-License-Identifier: Apache-2.0
   The glibc profile has no qualified fork/TLS/FD reconstruction protocol. */
#include <errno.h>
#include <unistd.h>
pid_t
__libc_fork (void)
{
  __set_errno (ENOSYS);
  return -1;
}
weak_alias (__libc_fork, __fork)
libc_hidden_def (__fork)
weak_alias (__libc_fork, fork)
stub_warning (fork)
