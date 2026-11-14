/* SPDX-License-Identifier: Apache-2.0 */
#include <string.h>
#include <tls.h>
#include <ldsodefs.h>
#include "xos_thread_tls.h"

#if !TLS_TCB_AT_TP || TLS_DTV_AT_TP
# error "XOS thread TLS requires the x86-64 TCB-at-TP layout"
#endif

int
__xos_thread_tls_initialize (const struct xos_thread_reservation *reservation,
                             struct pthread **out)
{
  struct xos_thread_tls_layout layout;
  if (__xos_thread_tls_layout (reservation, GLRO (dl_tls_static_size),
                               GLRO (dl_tls_static_align), TLS_TCB_SIZE,
                               &layout) != 0)
    return -1;
  struct pthread *pd = (struct pthread *) layout.thread_pointer;
  memset (pd, 0, sizeof (*pd));
  pd->header.self = pd;
  pd->header.tcb = pd;
  pd->header.multiple_threads = 1;
  pd->specific[0] = pd->specific_1stblock;
  pd->setxid_futex = -1;
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
