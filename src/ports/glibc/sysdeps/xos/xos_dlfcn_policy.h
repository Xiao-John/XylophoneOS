/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_DLFCN_POLICY_H
#define XOS_DLFCN_POLICY_H

#include <errno.h>
#include <ldsodefs.h>
#include <stddef.h>

#ifdef XOS_ONLINE_CLOSURE
extern int __xos_rtld_online_begin (const char *, long, int, int);
extern void __xos_rtld_online_end (void);
struct xos_dlfcn_request
{
  const char *name;
  long ns;
  int mode, closing;
};

static inline void
__xos_dlfcn_begin (void *argument)
{
  const struct xos_dlfcn_request *request = argument;
  const int error = __xos_rtld_online_begin (request->name, request->ns,
                                            request->mode, request->closing);
  if (error != 0)
    _dl_signal_error (error, request->name, NULL,
                      "XOS approved online library operation rejected");
}
#endif

static inline void
__xos_dlfcn_unsupported(void *ignored)
{
  (void) ignored;
  _dl_signal_error(ENOTSUP, NULL, NULL,
                   "XOS fixed closure does not support runtime loading");
}

#endif
