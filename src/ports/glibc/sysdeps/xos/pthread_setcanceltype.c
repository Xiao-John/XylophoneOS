/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>

int
__pthread_setcanceltype (int type, int *previous)
{
  if (type != PTHREAD_CANCEL_DEFERRED)
    return type == PTHREAD_CANCEL_ASYNCHRONOUS ? ENOTSUP : EINVAL;
  /* Every thread starts deferred and asynchronous requests are rejected.
     pthread_cancel also rejects delivery; no pending state is discarded. */
  if (previous != NULL)
    *previous = PTHREAD_CANCEL_DEFERRED;
  return 0;
}
libc_hidden_def (__pthread_setcanceltype)
weak_alias (__pthread_setcanceltype, pthread_setcanceltype)
