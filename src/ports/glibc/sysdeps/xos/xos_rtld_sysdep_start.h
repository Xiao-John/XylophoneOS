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
typedef void (*xos_rtld_dl_main) (const Elf64_Phdr *, Elf64_Word, Elf64_Addr *,
                                 Elf64_auxv_t *);

/* The file phase must remain live throughout the GNU callback and its
   later runtime handoff. */
extern struct xos_rtld_images __xos_rtld_start_images
  __attribute__ ((visibility ("hidden")));

/* Called after rtld self-relocation while its RELRO remains writable.
   On success images stays live until the file phase is finished. */
int __xos_rtld_prepare_sysdep_start (void **, struct xos_rtld_images *,
                                    struct xos_rtld_startup *)
  __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
