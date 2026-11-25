/* SPDX-License-Identifier: Apache-2.0 */
#include <atomic.h>
#include <libc-internal.h>
#include <pthreadP.h>
#include <stdlib.h>
#include "xos_thread_exit.h"
#include "xos_thread_name.h"

void
__xos_nptl_cleanup_current (void)
{
  call_function_static_weak (__call_tls_dtors);
  __nptl_deallocate_tsd ();
  __libc_thread_freeres ();
  __xos_thread_name_remove (__pthread_self ());
  /* exit's acquire load must observe all cleanup before it can proceed
     through the process termination barrier and global destructors. */
  atomic_fetch_add_release (&__nptl_nthreads, -1);
}

void
__xos_nptl_last_process_exit (void)
{
  exit (0);
}
