/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <semaphore.h>
#include <shlib-compat.h>

sem_t *
__sem_open (const char *name, int flags, ...)
{
  (void) name;
  (void) flags;
  /* XOS has no POSIX shared-object namespace. */
  __set_errno (ENOSYS);
  return SEM_FAILED;
}
stub_warning (sem_open)
versioned_symbol (libc, __sem_open, sem_open, GLIBC_2_34);
