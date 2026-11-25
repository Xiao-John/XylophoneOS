/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <semaphore.h>
#include <shlib-compat.h>

int
__sem_unlink (const char *name)
{
  (void) name;
  /* XOS has no POSIX shared-object namespace. */
  __set_errno (ENOSYS);
  return -1;
}
stub_warning (sem_unlink)
versioned_symbol (libc, __sem_unlink, sem_unlink, GLIBC_2_34);
