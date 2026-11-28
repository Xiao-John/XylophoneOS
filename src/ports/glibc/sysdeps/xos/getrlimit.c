/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <sys/resource.h>
#include "xos_file_limits.h"

int
__getrlimit (enum __rlimit_resource resource, struct rlimit *limits)
{
  if (limits == 0)
    {
      __set_errno (EFAULT);
      return -1;
    }
  if (resource != RLIMIT_NOFILE)
    {
      /* No other resource limit is enforced by this libc backend.  Do not
         advertise a synthetic infinity or write a partial answer. */
      __set_errno (resource < 0 || resource >= RLIM_NLIMITS ? EINVAL : ENOSYS);
      return -1;
    }
  limits->rlim_cur = limits->rlim_max = xos_file_descriptor_limit;
  return 0;
}
libc_hidden_def (__getrlimit)
weak_alias (__getrlimit, getrlimit)
