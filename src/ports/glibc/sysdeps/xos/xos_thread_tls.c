/* SPDX-License-Identifier: Apache-2.0 */
#include <string.h>
#include <tls.h>
#include <ldsodefs.h>
#include "xos_thread_tls.h"

#if !TLS_TCB_AT_TP || TLS_DTV_AT_TP
# error "XOS thread TLS requires the x86-64 TCB-at-TP layout"
#endif

static struct pthread *
initialize_descriptor (const struct xos_thread_tls_layout *layout)
{
  struct pthread *pd = (struct pthread *) layout->thread_pointer;
  memset (pd, 0, sizeof (*pd));
  pd->header.self = pd;
  pd->header.tcb = pd;
  pd->header.multiple_threads = 1;
  pd->specific[0] = pd->specific_1stblock;
  pd->setxid_futex = -1;
  return pd;
}

int
__xos_thread_tls_initialize (const struct xos_thread_reservation *reservation,
                             struct pthread **out)
{
  struct xos_thread_tls_layout layout;
  if (__xos_thread_tls_layout (reservation, GLRO (dl_tls_static_size),
                               GLRO (dl_tls_static_align), TLS_TCB_SIZE,
                               &layout) != 0)
    return -1;
  struct pthread *pd = initialize_descriptor (&layout);
  if (_dl_allocate_tls (TLS_TPADJ (pd)) == NULL)
    return -2;
  *out = pd;
  return 0;
}

void
__xos_thread_tls_release (struct pthread *pd)
{
  _dl_deallocate_tls (TLS_TPADJ (pd), false);
}

#if defined SHARED && defined XOS_ONLINE_CLOSURE
extern void __xos_dl_release_worker_dtv (void *);
enum { dtv_free, dtv_reserved, dtv_retired, dtv_draining };
static struct
{
  unsigned int state;
  void *dtv;
} retired_dtvs[XOS_WORKER_DTV_RETIRE_SLOTS];

void
__xos_thread_tls_drain (void)
{
  for (int slot = 0; slot < XOS_WORKER_DTV_RETIRE_SLOTS; ++slot)
    {
      unsigned int expected = dtv_retired;
      if (!__atomic_compare_exchange_n (&retired_dtvs[slot].state, &expected,
                                        dtv_draining, false, __ATOMIC_ACQUIRE,
                                        __ATOMIC_RELAXED))
        continue;
      /* The producer already ran all TLS destructors.  This pointer owns
         only heap allocations; no access to its old TCB is permitted. */
      __xos_dl_release_worker_dtv (retired_dtvs[slot].dtv);
      retired_dtvs[slot].dtv = NULL;
      __atomic_store_n (&retired_dtvs[slot].state, dtv_free, __ATOMIC_RELEASE);
    }
}

int
__xos_thread_tls_reserve (void)
{
  __xos_thread_tls_drain ();
  for (int slot = 0; slot < XOS_WORKER_DTV_RETIRE_SLOTS; ++slot)
    {
      unsigned int expected = dtv_free;
      if (__atomic_compare_exchange_n (&retired_dtvs[slot].state, &expected,
                                       dtv_reserved, false, __ATOMIC_ACQUIRE,
                                       __ATOMIC_RELAXED))
        return slot;
    }
  return -1;
}

void
__xos_thread_tls_cancel (int slot)
{
  if (slot < 0 || slot >= XOS_WORKER_DTV_RETIRE_SLOTS)
    __builtin_trap ();
  unsigned int expected = dtv_reserved;
  if (!__atomic_compare_exchange_n (&retired_dtvs[slot].state, &expected,
                                    dtv_free, false, __ATOMIC_RELEASE,
                                    __ATOMIC_RELAXED))
    __builtin_trap ();
}

void
__xos_thread_tls_retire (int slot, void *dtv)
{
  /* Called only after native begin_exit returned non-last.  Even a wake
     syscall is disallowed then: this publication must stay purely atomic. */
  if (slot < 0 || slot >= XOS_WORKER_DTV_RETIRE_SLOTS || dtv == NULL
      || __atomic_load_n (&retired_dtvs[slot].state, __ATOMIC_RELAXED)
           != dtv_reserved)
    __builtin_trap ();
  retired_dtvs[slot].dtv = dtv;
  __atomic_store_n (&retired_dtvs[slot].state, dtv_retired, __ATOMIC_RELEASE);
}
#endif

#ifdef SHARED
extern void *__xos_dl_init_reserved_worker_tls (void *, dtv_t *, size_t);

int
__xos_thread_shared_tls_initialize (
    const struct xos_thread_reservation *reservation, struct pthread **out)
{
#ifdef XOS_ONLINE_CLOSURE
  return __xos_thread_tls_initialize (reservation, out);
#else
  struct xos_thread_tls_layout layout;
  if (__xos_thread_tls_layout (reservation, GLRO (dl_tls_static_size),
                               GLRO (dl_tls_static_align), TLS_TCB_SIZE,
                               &layout) != 0)
    return -1;
  const xos_u64 padding = -layout.descriptor_end & (_Alignof (dtv_t) - 1);
  if (reservation->tls_end - layout.descriptor_end
      < padding + XOS_SHARED_DTV_SLOTS * sizeof (dtv_t))
    return -1;
  dtv_t *dtv = (dtv_t *) (layout.descriptor_end + padding);
  struct pthread *pd = initialize_descriptor (&layout);
  memset (dtv, 0, XOS_SHARED_DTV_SLOTS * sizeof (*dtv));
  if (__xos_dl_init_reserved_worker_tls (TLS_TPADJ (pd), dtv,
                                        XOS_SHARED_DTV_SLOTS) == NULL)
    return -2;
  *out = pd;
  return 0;
#endif
}
#else
extern void *__xos_dl_init_reserved_tls (void *, dtv_t *)
  __attribute__ ((visibility ("hidden")));

int
__xos_thread_static_tls_initialize (
    const struct xos_thread_reservation *reservation, struct pthread **out)
{
  struct xos_thread_tls_layout layout;
  if (__xos_thread_tls_layout (reservation, GLRO (dl_tls_static_size),
                               GLRO (dl_tls_static_align), TLS_TCB_SIZE,
                               &layout) != 0)
    return -1;
  xos_u64 alignment = _Alignof (dtv_t);
  xos_u64 padding = -layout.descriptor_end & (alignment - 1);
  if (reservation->tls_end - layout.descriptor_end
      < padding + 3 * sizeof (dtv_t))
    return -1;
  dtv_t *dtv = (dtv_t *) (layout.descriptor_end + padding);
  struct pthread *pd = initialize_descriptor (&layout);
  if (__xos_dl_init_reserved_tls (TLS_TPADJ (pd), dtv) == NULL)
    return -2;
  *out = pd;
  return 0;
}
#endif
