/* SPDX-License-Identifier: Apache-2.0 */
/* Build using the GNU interpreter's actual internal data declarations. */
#include <ldsodefs.h>
#include <string.h>
#include <unistd.h>
#include "xos_rtld_sysdep_start.h"

extern char **_environ attribute_hidden;

int d1_gnu_startup_matches (void **, const struct xos_rtld_startup *, int);

int
d1_gnu_startup_matches (void **stack, const struct xos_rtld_startup *startup,
                        int expected_secure)
{
  struct xos_d1_entry_view view;
  if (!__xos_rtld_check_entry (stack, &view))
    return 0;
  if (_dl_argc != view.argc || _dl_argv != (char **) view.argv
      || _environ != (char **) view.environment || GLRO (dl_auxv) != startup->auxv
      || startup->auxv != (void *) view.auxv || GLRO (dl_pagesize) != 4096
      || __libc_stack_end != stack || __libc_enable_secure != expected_secure
      || startup->phdr != (void *) view.record->main_phdr
      || startup->phnum != view.record->main_phnum
      || startup->user_entry != view.record->main_entry)
    return 0;
  int entropy = 0;
  for (const Elf64_auxv_t *a = startup->auxv; a->a_type != AT_NULL; ++a)
    if (a->a_type == AT_RANDOM)
      entropy = _dl_random == (void *) a->a_un.a_val;
  int environment = 0;
  for (char **str = _environ; *str != NULL; ++str)
    if (strcmp (*str, "D1_ENTRY_ENV=verified") == 0)
      environment = 1;
  return entropy && environment && _dl_argc == 2
         && strcmp (_dl_argv[1], expected_secure ? "secure" : "ordinary") == 0;
}
