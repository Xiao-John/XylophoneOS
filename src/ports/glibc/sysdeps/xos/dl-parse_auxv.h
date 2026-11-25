/* SPDX-License-Identifier: Apache-2.0
   Private CRT-to-libc startup data, constructed by the XOS CRT.  */
#include <elf.h>
#include <fpu_control.h>
#include <ldsodefs.h>
#include <link.h>
#include <unistd.h>

typedef ElfW(Addr) dl_parse_auxv_t[AT_MINSIGSTKSZ + 1];

static inline void
_dl_parse_auxv (ElfW(auxv_t) *av, dl_parse_auxv_t values)
{
  values[AT_PAGESZ] = 4096;
  values[AT_FPUCW] = _FPU_DEFAULT;
  for (; av->a_type != AT_NULL; ++av)
    if (av->a_type <= AT_MINSIGSTKSZ)
      values[av->a_type] = av->a_un.a_val;
  GLRO (dl_pagesize) = values[AT_PAGESZ];
  GLRO (dl_fpu_control) = values[AT_FPUCW];
  GLRO (dl_clktck) = 100;
  __libc_enable_secure = values[AT_SECURE];
  _dl_random = (void *) values[AT_RANDOM];
}
