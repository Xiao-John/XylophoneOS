/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthread.h>
int __pthread_cancel (pthread_t);
int main (void)
{
  errno = EINVAL;
  if (__pthread_cancel (pthread_self ()) != ENOTSUP || errno != EINVAL) return 1;
  return 0;
}
