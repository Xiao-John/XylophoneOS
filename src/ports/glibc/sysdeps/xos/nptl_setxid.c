/* SPDX-License-Identifier: Apache-2.0
   XOS has no implemented POSIX credential-switching protocol. */
#include <errno.h>
#include <signal.h>

struct xid_command;

/* The generic NPTL implementation sends Linux SIGSETXID to threads and
   invokes a Linux set*id syscall.  XOS authority is not derived from such
   identifiers and no equivalent credential transition is implemented. */
__attribute__ ((visibility ("hidden"))) int
__nptl_setxid (struct xid_command *command)
{
  (void) command;
  errno = ENOSYS;
  return -1;
}

__attribute__ ((visibility ("hidden"))) void
__nptl_setxid_sighandler (int signal_number, siginfo_t *info, void *context)
{
  (void) signal_number; (void) info; (void) context;
  /* No signal-based credential transition may run on this backend.  */
  __builtin_trap ();
}
