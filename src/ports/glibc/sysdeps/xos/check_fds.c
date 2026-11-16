/* SPDX-License-Identifier: Apache-2.0
   Fail closed if glibc requests secure standard-descriptor verification.  */
#include <unistd.h>

void
__libc_check_standard_fds (void)
{
  /* XOS has no glibc-qualified secure-execution and trusted /dev/null
     contract yet.  Never continue a secure launch without that contract.  */
  _exit (127);
}
