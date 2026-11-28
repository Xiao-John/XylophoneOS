/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_SLEEP_H
#define XOS_SLEEP_H 1

#include <pthread.h>
#include <stdint.h>

#define XOS_SLEEP_TICKET_VERSION 1U
#define XOS_SLEEP_CAPACITY 4U

/* One active elapsed-time wait, local to the process which issued it.
   Copying this value never grants access to another process.  */
struct xos_sleep_ticket
{
  uint32_t version, size, reserved, reserved2;
  uint64_t pid, tid, sequence, deadline_ns;
};

#ifdef __cplusplus
extern "C" {
#endif
/* Return an error number without changing errno.  Query only publishes a
   ticket while the named thread has an active sleep.  A successful interrupt
   targets exactly that wait; it is neither a signal nor pthread cancellation.
   See docs/contracts/libc_timed_waits.md for the race and lifetime rules.  */
int xos_sleep_query (pthread_t, struct xos_sleep_ticket *);
int xos_sleep_interrupt (const struct xos_sleep_ticket *);
#ifdef __cplusplus
}
#endif
#endif
