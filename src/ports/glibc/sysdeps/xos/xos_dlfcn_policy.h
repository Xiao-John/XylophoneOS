/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_DLFCN_POLICY_H
#define XOS_DLFCN_POLICY_H

#include <errno.h>
#include <ldsodefs.h>
#include <stddef.h>

static inline void
__xos_dlfcn_unsupported(void *ignored)
{
  (void) ignored;
  _dl_signal_error(ENOTSUP, NULL, NULL,
                   "XOS fixed closure does not support runtime loading");
}

#endif
