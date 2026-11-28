/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <unistd.h>
#ifndef SHARED
# include <pthreadP.h>
# include <sys/single_threaded.h>
# include "xos_thread_identity.h"
# include "xos_thread_name.h"
# include "xos_file_runtime.h"
# include "xos_timer.h"
# include "xos_sleep.h"
#endif

pid_t
_Fork (void)
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
  const long child = __xos_file_fork ();
  if (child < 0)
    {
      __set_errno (-child);
      return -1;
    }
  if (child == 0)
    {
      struct xos_thread_info info;
      if (xos_thread_lifecycle (41, (xos_u64) &info, 0) != 0
          || info.tid == 0 || info.tid > FUTEX_TID_MASK
          || info.thread_pointer != (xos_u64) THREAD_SELF)
        _exit (127);
      const xos_u64 previous_tid = THREAD_GETMEM (THREAD_SELF, tid);
      THREAD_SETMEM (THREAD_SELF, tid, info.tid);
      __xos_thread_name_after_fork (previous_tid, info.tid);
      __xos_timer_after_fork ();
      __xos_sleep_after_fork ();
    }
  return (pid_t) child;
#endif
}
libc_hidden_def (_Fork)
#ifdef SHARED
stub_warning (_Fork)
#endif
