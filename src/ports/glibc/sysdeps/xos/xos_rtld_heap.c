/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "xos_rtld_heap.h"
#include "xos_file_trap.h"

enum heap_phase { heap_idle, heap_open, heap_sealed };
static struct
{
  uint64_t base, bytes, used, deadline;
  enum heap_phase phase;
} heap;

static int
heap_time_error (uint64_t deadline)
{
  const long now = file_trap (46, 0, 0, 0);
  if (now < 0)
    return EIO;
  return (uint64_t) now >= deadline ? ETIMEDOUT : 0;
}

int
__xos_rtld_heap_begin (const struct xos_rtld_heap_plan *plan)
{
  if (heap.phase != heap_idle)
    return EBUSY;
  if (!xos_rtld_heap_plan_valid (plan))
    return EINVAL;
  const int error = heap_time_error (plan->deadline_ns);
  if (error != 0)
    return error;
  heap.base = plan->base;
  heap.bytes = plan->bytes;
  heap.deadline = plan->deadline_ns;
  heap.phase = heap_open;
  return 0;
}

static uint64_t
batch_bytes (uint64_t remaining)
{
  const uint64_t maximum = (uint64_t) XOS_VM_MAX_CHANGE_PAGES * XOS_VM_PAGE;
  return remaining < maximum ? remaining : maximum;
}

static void
rollback_heap (uint64_t start, uint64_t committed)
{
  for (uint64_t at = 0; at < committed;)
    {
      const uint64_t batch = batch_bytes (committed - at);
      if (xos_image_vm (XOS_VM_DECOMMIT, 0, start + at, batch, 0, 0) != 0)
        {
          static const char error[] = "XOS rtld: cannot roll back early heap\n";
          (void) file_trap (11, 2, (xos_u64) error, sizeof (error) - 1);
          (void) file_trap (2, 127, 0, 0);
          __builtin_trap ();
        }
      at += batch;
    }
}

void *
__xos_rtld_heap_grow (size_t bytes)
{
  if (heap.phase != heap_open || bytes == 0 || bytes % XOS_VM_PAGE != 0
      || bytes > heap.bytes - heap.used)
    return XOS_RTLD_HEAP_FAILED;
  const uint64_t start = heap.base + heap.used;
  uint64_t committed = 0;
  while (committed < bytes)
    {
      const uint64_t batch = batch_bytes (bytes - committed);
      if (heap_time_error (heap.deadline) != 0
          || xos_image_vm (XOS_VM_COMMIT, 0, start + committed, batch, 0, 3) != 0)
        {
          rollback_heap (start, committed);
          return XOS_RTLD_HEAP_FAILED;
        }
      committed += batch;
    }
  if (heap_time_error (heap.deadline) != 0)
    {
      rollback_heap (start, committed);
      return XOS_RTLD_HEAP_FAILED;
    }
  heap.used += bytes;
  return (void *) start;
}

uint64_t
__xos_rtld_heap_deadline (void)
{
  return heap.phase == heap_open ? heap.deadline : 0;
}

int
__xos_rtld_heap_seal (void)
{
  if (heap.phase != heap_open)
    return EINVAL;
  heap.phase = heap_sealed;
  return heap_time_error (heap.deadline);
}
