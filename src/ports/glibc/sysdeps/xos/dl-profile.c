/* SPDX-License-Identifier: Apache-2.0 */
#include <ldsodefs.h>

void
_dl_start_profile (void)
{
  _dl_fatal_printf ("LD_PROFILE is not supported on XOS\n");
}

/* Profiling cannot be active. The shared PLT audit path still calls this
   entry, so retain the ordinary inactive behavior. */
void
_dl_mcount (ElfW(Addr) frompc, ElfW(Addr) selfpc)
{
  (void) frompc;
  (void) selfpc;
}
rtld_hidden_def (_dl_mcount)
