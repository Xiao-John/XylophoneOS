/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <errno.h>
#include <shlib-compat.h>

int
__pthread_tryjoin_np (pthread_t thread, void **value)
{
  /* SYS44 always waits for a live joinable thread. A probe followed by a
     blocking syscall could also race another joiner. */
  (void) thread;
  (void) value;
  return ENOTSUP;
}
versioned_symbol (libc, __pthread_tryjoin_np, pthread_tryjoin_np, GLIBC_2_34);
