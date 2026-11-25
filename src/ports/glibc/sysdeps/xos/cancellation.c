/* SPDX-License-Identifier: Apache-2.0
   Explicit failure for cancellable syscall operations not yet supported by XOS. */
#include <errno.h>
#include <syscall_types.h>

/* The XOS kernel has no qualified asynchronous cancellation protocol.
   Never issue an operation here with cancellation silently disabled. */
__attribute__ ((visibility ("hidden"))) long int
__internal_syscall_cancel (__syscall_arg_t a1, __syscall_arg_t a2,
                           __syscall_arg_t a3, __syscall_arg_t a4,
                           __syscall_arg_t a5, __syscall_arg_t a6,
                           __syscall_arg_t nr)
{
  (void) a1; (void) a2; (void) a3; (void) a4;
  (void) a5; (void) a6; (void) nr;
  return -ENOSYS;
}

__attribute__ ((visibility ("hidden"))) long int
__syscall_cancel (__syscall_arg_t a1, __syscall_arg_t a2,
                  __syscall_arg_t a3, __syscall_arg_t a4,
                  __syscall_arg_t a5, __syscall_arg_t a6,
                  __syscall_arg_t nr)
{
  (void) a1; (void) a2; (void) a3; (void) a4;
  (void) a5; (void) a6; (void) nr;
  errno = ENOSYS;
  return -1;
}

__attribute__ ((visibility ("hidden"))) _Noreturn void
__syscall_do_cancel (void)
{
  /* No valid XOS cancellation unwinding protocol is installed. */
  __builtin_trap ();
}
