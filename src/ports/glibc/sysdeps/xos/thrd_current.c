/* SPDX-License-Identifier: Apache-2.0 */
#include <pthreadP.h>
#include <threads.h>

thrd_t
thrd_current (void)
{
  return __pthread_self ();
}
