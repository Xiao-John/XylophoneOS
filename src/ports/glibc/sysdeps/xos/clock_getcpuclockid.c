/* SPDX-License-Identifier: Apache-2.0
   The existing CPU accounting ABI only selects the calling process. */
#include <errno.h>
#include <time.h>
#include <unistd.h>

int
__clock_getcpuclockid (pid_t pid, clockid_t *clock)
{
  const int saved_errno = errno;
  int error = 0;
  if (clock == NULL)
    error = EINVAL;
  else if (pid < 0)
    error = ESRCH;
  else if (pid != 0)
    {
      pid_t self = __getpid ();
      if (self < 0)
        error = errno;
      else if (pid != self)
        error = ENOSYS;
    }
  if (error == 0)
    {
      struct timespec resolution;
      if (__clock_getres (CLOCK_PROCESS_CPUTIME_ID, &resolution) != 0)
        error = errno;
      else
        *clock = CLOCK_PROCESS_CPUTIME_ID;
    }
  /* This function returns an error number, not -1/errno. */
  __set_errno (saved_errno);
  return error;
}
weak_alias (__clock_getcpuclockid, clock_getcpuclockid)
