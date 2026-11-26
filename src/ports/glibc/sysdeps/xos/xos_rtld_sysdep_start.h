/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_SYSDEP_START_H
#define XOS_RTLD_SYSDEP_START_H
#include "xos_rtld_mapping.h"

struct xos_rtld_startup
{
  const Elf64_Phdr *phdr;
  Elf64_Word phnum;
  Elf64_Addr user_entry;
  Elf64_auxv_t *auxv;
};

#ifdef __cplusplus
extern "C" {
#endif
/* Called after rtld self-relocation while its RELRO remains writable.
   On success images stays live until the file phase is finished. */
int __xos_rtld_prepare_sysdep_start (void **, struct xos_rtld_images *,
                                    struct xos_rtld_startup *)
  __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
