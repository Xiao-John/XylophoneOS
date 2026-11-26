/* SPDX-License-Identifier: Apache-2.0 */
#if defined SHARED && IS_IN (rtld)
# include "xos_rtld_initial_tp.h"

static inline void
call_tls_init_tp (void *address)
{
  __xos_rtld_install_initial_tp (address);
}
#else
# include_next <dl-call_tls_init_tp.h>
#endif
