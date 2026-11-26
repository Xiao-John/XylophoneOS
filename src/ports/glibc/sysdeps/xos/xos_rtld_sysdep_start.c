/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <ldsodefs.h>
#include <dl-parse_auxv.h>
#include "xos_rtld_sysdep_start.h"

extern char **_environ attribute_hidden;

int __libc_enable_secure attribute_relro;
rtld_hidden_data_def (__libc_enable_secure)
void *__libc_stack_end attribute_relro;
rtld_hidden_data_def (__libc_stack_end)
void *_dl_random attribute_relro;

int
__xos_rtld_prepare_sysdep_start (void **stack, struct xos_rtld_images *images,
                                struct xos_rtld_startup *startup)
{
  if (startup == NULL)
    return EINVAL;
  struct xos_d1_entry_view view;
  const int result = __xos_rtld_attach_entry_images (stack, images, &view);
  if (result != 0)
    return result;

  dl_parse_auxv_t values = { 0 };
  Elf64_auxv_t *auxv = (void *) view.auxv;
  _dl_parse_auxv (auxv, values);
  _dl_argc = view.argc;
  _dl_argv = (void *) view.argv;
  _environ = (void *) view.environment;
  GLRO (dl_auxv) = auxv;
  __libc_stack_end = stack;
  *startup = (struct xos_rtld_startup) {
    (const void *) values[AT_PHDR], values[AT_PHNUM], values[AT_ENTRY], auxv
  };
  return 0;
}
