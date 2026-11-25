/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <sys/mman.h>
#include <shlib-compat.h>

int
__shm_unlink (const char *name)
{
  (void) name;
  /* XOS has no POSIX shared-object namespace. */
  __set_errno (ENOSYS);
  return -1;
}
stub_warning (shm_unlink)
versioned_symbol (libc, __shm_unlink, shm_unlink, GLIBC_2_34);
