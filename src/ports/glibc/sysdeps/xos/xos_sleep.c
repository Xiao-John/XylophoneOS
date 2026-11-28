/* SPDX-License-Identifier: Apache-2.0
   Process-local, per-wait interruption over native wait-word.  No signal,
   cancellation state, kernel object or external service is involved.  */
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <string.h>
#include <shlib-compat.h>
#include "xos/sleep.h"
#include "xos_clock.h"
#include "xos_sleep.h"
#include "xos_thread_identity.h"

extern void __libc_fatal (const char *)
  __attribute__ ((noreturn, visibility ("hidden")));

_Static_assert (sizeof (struct xos_sleep_ticket) == 48, "sleep ticket v1");
_Static_assert (__builtin_offsetof (struct xos_sleep_ticket, pid) == 16,
                "sleep ticket identity offset");

struct sleep_slot
{
  struct xos_sleep_ticket ticket;
  xos_u32 interrupted;
};

static struct sleep_slot sleep_slots[XOS_SLEEP_CAPACITY];
static xos_u32 sleep_lock;
static xos_u64 sleep_sequence;

static int
wait_error (long status)
{
  switch (status)
    {
    case -11: return EFAULT;
    case -12: return EBUSY;
    case -5: case -17: return ENOMEM;
    case -18: return ENOTSUP;
    default: return EIO;
    }
}

static int
lock_sleep (void)
{
  while (__atomic_exchange_n (&sleep_lock, 1, __ATOMIC_ACQUIRE))
    {
      long result = __xos_wait_word (&sleep_lock, 1, ~(xos_u64) 0);
      if (result != 0 && result != -14)
        return wait_error (result);
    }
  return 0;
}

static void
unlock_sleep (void)
{
  __atomic_store_n (&sleep_lock, 0, __ATOMIC_RELEASE);
  __xos_wake_word (&sleep_lock, 1);
}

void
__xos_sleep_after_fork (void)
{
  /* Native fork admits one thread.  Never copy a wait or an interrupt into
     the child even if a future runtime adds another fork entry path.  */
  memset (sleep_slots, 0, sizeof (sleep_slots));
  sleep_lock = 0;
  sleep_sequence = 0;
}

int
__xos_sleep_query (pthread_t target, struct xos_sleep_ticket *output)
{
  if (output == NULL)
    return EFAULT;
  if ((xos_u64) target == 0)
    return EINVAL;
  int error = lock_sleep ();
  if (error != 0)
    return error;
  error = ESRCH;
  struct xos_sleep_ticket ticket;
  for (unsigned int index = 0; index < XOS_SLEEP_CAPACITY; ++index)
    if (sleep_slots[index].ticket.tid == (xos_u64) target)
      {
        ticket = sleep_slots[index].ticket;
        error = 0;
        break;
      }
  unlock_sleep ();
  if (error == 0)
    *output = ticket;
  return error;
}
versioned_symbol (libc, __xos_sleep_query, xos_sleep_query, GLIBC_2_44);

int
__xos_sleep_interrupt (const struct xos_sleep_ticket *input)
{
  if (input == NULL)
    return EFAULT;
  const struct xos_sleep_ticket ticket = *input;
  if (ticket.version != XOS_SLEEP_TICKET_VERSION
      || ticket.size != sizeof (ticket) || ticket.reserved != 0
      || ticket.reserved2 != 0 || ticket.pid == 0 || ticket.tid == 0
      || ticket.sequence == 0 || ticket.deadline_ns == 0
      || ticket.deadline_ns > LONG_MAX)
    return EINVAL;
  struct xos_thread_info self;
  long native = xos_thread_lifecycle (41, (xos_u64) &self, 0);
  if (native != 0)
    return xos_thread_lifecycle_error (native);
  if (ticket.pid != self.pid)
    return EPERM;
  int error = lock_sleep ();
  if (error != 0)
    return error;
  error = ESRCH;
  for (unsigned int index = 0; index < XOS_SLEEP_CAPACITY; ++index)
    {
      struct sleep_slot *slot = &sleep_slots[index];
      if (slot->ticket.pid != ticket.pid || slot->ticket.tid != ticket.tid
          || slot->ticket.sequence != ticket.sequence
          || slot->ticket.deadline_ns != ticket.deadline_ns)
        continue;
      long now = __xos_clock_trap (46, 0);
      if (__atomic_load_n (&slot->interrupted, __ATOMIC_ACQUIRE))
        error = EALREADY;
      else if (now < 0)
        error = EOVERFLOW;
      else if ((xos_u64) now >= ticket.deadline_ns)
        error = ETIMEDOUT;
      else
        {
          /* The word comparison and native enqueue are atomic with respect
             to wake-word: an interrupt before enqueue cannot be lost.  */
          __atomic_store_n (&slot->interrupted, 1, __ATOMIC_RELEASE);
          native = __xos_wake_word (&slot->interrupted, 1);
          /* A failed wake cannot safely undo an already visible interrupt.
             Report the real failure; the waiter still sees the committed
             word at its original deadline.  No retry is performed here. */
          error = native >= 0 ? 0 : wait_error (native);
        }
      break;
    }
  unlock_sleep ();
  return error;
}
versioned_symbol (libc, __xos_sleep_interrupt, xos_sleep_interrupt, GLIBC_2_44);

int
__xos_sleep_until (xos_u64 deadline, xos_u64 *remaining)
{
  struct xos_thread_info self;
  long native = xos_thread_lifecycle (41, (xos_u64) &self, 0);
  if (native != 0)
    return xos_thread_lifecycle_error (native);
  int error = lock_sleep ();
  if (error != 0)
    return error;
  struct sleep_slot *slot = NULL;
  for (unsigned int index = 0; index < XOS_SLEEP_CAPACITY; ++index)
    if (sleep_slots[index].ticket.tid == 0)
      {
        slot = &sleep_slots[index];
        break;
      }
  if (slot == NULL || sleep_sequence == ~(xos_u64) 0)
    {
      unlock_sleep ();
      return slot == NULL ? EAGAIN : EOVERFLOW;
    }
  slot->ticket = (struct xos_sleep_ticket) {
    .version = XOS_SLEEP_TICKET_VERSION, .size = sizeof (slot->ticket),
    .pid = self.pid, .tid = self.tid, .sequence = ++sleep_sequence,
    .deadline_ns = deadline
  };
  __atomic_store_n (&slot->interrupted, 0, __ATOMIC_RELEASE);
  unlock_sleep ();

  for (;;)
    {
      native = __xos_wait_word (&slot->interrupted, 0, deadline);
      error = lock_sleep ();
      if (error != 0)
        /* Once published, the slot must be retired under its lock. An
           unusable private synchronization mechanism cannot safely return
           while retaining an interruptible entry owned by this call. */
        __libc_fatal ("XOS sleep: cannot retire an active wait\n");
      long now = __xos_clock_trap (46, 0);
      if (__atomic_load_n (&slot->interrupted, __ATOMIC_ACQUIRE))
        {
          error = now < 0 ? EOVERFLOW : EINTR;
          if (error == EINTR && remaining != NULL)
            *remaining = (xos_u64) now < deadline ? deadline - now : 0;
        }
      else if (now < 0)
        error = EOVERFLOW;
      else if (native != 0 && native != -14 && native != -13)
        /* A late native failure is still a failure. Reaching the requested
           time does not make an unsupported or failed wait succeed. */
        error = wait_error (native);
      else if ((xos_u64) now >= deadline)
        error = 0;
      else
        {
          /* Spurious/early wakeups keep the original absolute deadline. */
          unlock_sleep ();
          continue;
        }
      slot->ticket = (struct xos_sleep_ticket) {0};
      __atomic_store_n (&slot->interrupted, 0, __ATOMIC_RELEASE);
      unlock_sleep ();
      return error;
    }
}
