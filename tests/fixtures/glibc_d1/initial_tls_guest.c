/* SPDX-License-Identifier: Apache-2.0 */
/* Compile with GNU's rtld flags and internal TCB/DTV layout. */
#include <ldsodefs.h>
#include <pthreadP.h>
#include <dl-call_tls_init_tp.h>
#include "xos_file_trap.h"
#include "xos_rtld_heap.h"
#include "xos_thread_identity.h"

void *__minimal_malloc (size_t);

static __attribute__ ((noreturn)) void
stop (const char *message, size_t size, int code)
{
  (void) file_trap (11, 1, (uintptr_t) message, size);
  (void) file_trap (2, code, 0, 0);
  __builtin_trap ();
}

#define CHECK(condition, reason)                               \
  do                                                           \
    {                                                          \
      if (!(condition))                                        \
        {                                                      \
          static const char m[] = "D1_INITIAL_TP_FAIL " reason "\n"; \
          stop (m, sizeof (m) - 1, 61);                         \
        }                                                      \
    }                                                          \
  while (0)

void __xos_glibc_start (const void *, void *) __attribute__ ((noreturn));

void
__xos_glibc_start (const void *startup, void *stack)
{
  (void) startup;
  const long now = file_trap (46, 0, 0, 0);
  CHECK (now >= 0, "native monotonic time");
  const struct xos_rtld_heap_plan plan = {
    .base = 0x120000200000UL,
    .bytes = 8 * XOS_VM_PAGE,
    .deadline_ns = (xos_u64) now + 5000000000UL,
  };
  CHECK (xos_image_vm (XOS_VM_RESERVE, XOS_VM_EXACT, plan.base, plan.bytes,
                       XOS_VM_PAGE, 0) == plan.base
         && __xos_rtld_heap_begin (&plan) == 0,
         "private native heap");

  void *block = __minimal_malloc (XOS_VM_PAGE + sizeof (struct pthread)
                                  + TCB_ALIGNMENT);
  CHECK (block != NULL, "GNU early TLS storage");
  const uintptr_t address = ((uintptr_t) block + TCB_ALIGNMENT - 1)
                            & ~(TCB_ALIGNMENT - 1);
  struct pthread *pd = (void *) address;
  CHECK (address >= plan.base && address < plan.base + plan.bytes,
         "high anonymous address");

  /* The fixture supplies already prepared storage. It exercises NPTL's
     native install and completion rather than the loader's TLS layout. */
  dtv_t *storage = __minimal_malloc (4 * sizeof (*storage));
  volatile unsigned char *value = __minimal_malloc (1);
  CHECK (storage != NULL && value != NULL && *value == 0, "early DTV storage");
  *value = 0x71;
  storage[0].counter = 2;
  storage[1].counter = 1;
  storage[2].pointer.val = (void *) value;
  INSTALL_DTV (pd, storage);
  GL (dl_initial_dtv) = GET_DTV (pd);

  struct xos_thread_info before, after;
  CHECK (xos_thread_lifecycle (41, (uintptr_t) &before, 0) == 0
         && before.thread_pointer != address, "existing native thread");
  __tls_pre_init_tp ();
  call_tls_init_tp (pd);
  CHECK (xos_thread_lifecycle (41, (uintptr_t) &after, 0) == 0
         && after.thread_pointer == address && after.tid == before.tid
         && pd->tid == after.tid, "native TP and TID");
  CHECK (THREAD_SELF == pd && pd->header.tcb == pd && pd->header.self == pd
         && pd->specific[0] == &pd->specific_1stblock[0]
         && pd->joinstate == THREAD_STATE_JOINABLE
         && GL (dl_stack_user).next == &pd->list,
         "actual GNU NPTL TCB");
  CHECK (after.stack_top == before.stack_top
         && after.stack_bottom == before.stack_bottom
         && (uintptr_t) stack >= after.stack_bottom
         && (uintptr_t) stack <= after.stack_top
         && pd->stackblock == (void *) after.stack_bottom
         && pd->stackblock_size == after.stack_top - after.stack_bottom,
         "exact native main stack");
  CHECK (__xos_rtld_heap_seal () == 0, "seal initial storage");

  const long deadline = file_trap (46, 0, 0, 0) + 40000000L;
  CHECK (file_trap (47, deadline, 0, 0) == 0
         && file_trap (46, 0, 0, 0) >= deadline, "native dispatch");
  dtv_t *dtv = THREAD_DTV ();
  CHECK (THREAD_SELF == pd && dtv == GL (dl_initial_dtv)
         && dtv == &storage[1] && dtv[-1].counter == 2
         && dtv[0].counter == 1 && dtv[1].pointer.val == (void *) value
         && *value == 0x71, "TCB and DTV after dispatch");

  static const char success[] = "D1_INITIAL_TP_OK tcb=gnu tid=native "
                               "stack=exact dtv=preserved dispatch=preserved\n";
  stop (success, sizeof (success) - 1, 0);
}
