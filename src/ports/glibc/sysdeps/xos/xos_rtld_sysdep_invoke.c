/* SPDX-License-Identifier: Apache-2.0 */
#include <ldsodefs.h>
#include <dl-hwcap-check.h>
#include <dl-machine.h>
#include <dl-tunables.h>
#include <startup.h>
#include <string.h>
#include <unistd.h>
#include "xos_d1_environment.h"
#include "xos_rtld_sysdep_start.h"

/* The x86 rtld uses the upstream CPU tunable callbacks in its sysdep
   startup object. The separate libc object serves static startup. */
#include <sysdeps/x86/cpu-tunables.c>

extern char **_environ attribute_hidden;
struct xos_rtld_images __xos_rtld_start_images;

ElfW(Addr)
_dl_sysdep_start (void **start_argptr, xos_rtld_dl_main dl_main)
{
  struct xos_rtld_startup startup;
  if (__xos_rtld_prepare_sysdep_start (start_argptr, &__xos_rtld_start_images,
                                      &startup) != 0)
    _startup_fatal ("XOS rtld: invalid native startup handoff\n");
  for (char **arg = _environ; *arg != NULL; ++arg)
    if (!xos_d1_environment_allowed (*arg))
      _startup_fatal ("XOS rtld: unsupported loader environment\n");
  if (__libc_enable_secure)
    _startup_fatal ("XOS rtld: secure descriptor startup is unavailable\n");

  /* The fixed startup profile uses GNU defaults and keeps the validated
     environment available to dl_main and the application. */
  char *default_tunables[] = { NULL };
  dl_hwcap_check ();
  __tunables_init (default_tunables, _dl_argv);
  _dl_sort_maps_init ();
#ifdef DL_PLATFORM_INIT
  DL_PLATFORM_INIT;
#endif
  if (GLRO (dl_platform) != NULL)
    GLRO (dl_platformlen) = strlen (GLRO (dl_platform));

  dl_main (startup.phdr, startup.phnum, &startup.user_entry, startup.auxv);
  return startup.user_entry;
}
