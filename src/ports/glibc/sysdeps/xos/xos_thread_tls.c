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

#ifdef SHARED
extern void *__xos_dl_init_reserved_worker_tls (void *, dtv_t *, size_t);

int
__xos_thread_shared_tls_initialize (
    const struct xos_thread_reservation *reservation, struct pthread **out)
{
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
