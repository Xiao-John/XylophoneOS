/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <unistd.h>
#ifndef SHARED
# include <pthreadP.h>
# include <register-atfork.h>
# include <sys/single_threaded.h>
#endif

pid_t
__libc_fork (void)
{
#ifdef SHARED
  __set_errno (ENOSYS);
  return -1;
#else
  if (!__libc_single_threaded_internal)
    {
      __set_errno (ENOTSUP);
      return -1;
    }
  const uint64_t handlers = __run_prefork_handlers (false);
  const pid_t child = _Fork ();
  const int error = errno;
  if (child == 0)
    __fork_generation += __PTHREAD_ONCE_FORK_GEN_INCR;
  __run_postfork_handlers (child == 0 ? atfork_run_child : atfork_run_parent,
                          false, handlers);
  if (child < 0)
    __set_errno (error);
  return child;
#endif
}
weak_alias (__libc_fork, __fork)
libc_hidden_def (__fork)
weak_alias (__libc_fork, fork)
#ifdef SHARED
stub_warning (fork)
#endif
