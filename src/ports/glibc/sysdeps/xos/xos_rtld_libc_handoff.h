/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_LIBC_HANDOFF_H
#define XOS_RTLD_LIBC_HANDOFF_H
#include "xos_rtld_mapping.h"

struct link_map;
int __xos_rtld_handoff_libc_files (struct link_map *, struct xos_rtld_images *)
  __attribute__ ((visibility ("hidden")));
#endif
