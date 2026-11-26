/* SPDX-License-Identifier: Apache-2.0 */
#include <elf.h>
#include "xos_d1_start.h"

static int
startup_text (xos_u64 pointer)
{
  if (pointer < XOS_D1_STARTUP_BEGIN || pointer >= XOS_D1_STACK_TOP)
    return 0;
  const char *text = (const void *) pointer;
  for (xos_u64 i = 0; i < 4096 && i < XOS_D1_STACK_TOP - pointer; ++i)
    if (text[i] == 0)
      return 1;
  return 0;
}

int
__xos_rtld_check_entry (void **start_argptr, struct xos_d1_entry_view *output)
{
  const xos_u64 address = (xos_u64) start_argptr;
  if (output == 0 || address < XOS_D1_STACK_BOTTOM
      || address > XOS_D1_STARTUP_BEGIN - sizeof (struct xos_d1_entry_handoff)
      || (address & 15) != 0)
    return 0;
  struct xos_d1_entry_handoff *handoff = (void *) start_argptr;
  struct xos_d1_entry_record *record = &handoff->record;
  if (record->magic != XOS_D1_ENTRY_MAGIC || record->version != XOS_D1_ENTRY_VERSION
      || record->size != sizeof (*record) || record->main_phnum == 0
      || record->main_phnum > 64 || record->main_entry == record->interpreter_entry
      || record->files.phase != xos_file_session_active || record->files.owner_pid == 0
      || record->files.request_sequence == 0)
    return 0;

  xos_u64 *args = handoff->stack.words;
  const xos_u64 argc = *args++;
  if (argc == 0 || argc > XOS_D1_MAX_ARGS || args[argc] != 0)
    return 0;
  for (xos_u64 i = 0; i < argc; ++i)
    if (!startup_text (args[i]))
      return 0;
  xos_u64 *environment = args + argc + 1;
  xos_u64 *auxv = environment;
  while (*auxv != 0)
    {
      if (auxv - environment == XOS_D1_MAX_ENVIRONMENT || !startup_text (*auxv))
        return 0;
      ++auxv;
    }
  ++auxv;
  /* This stack is built only by the checked bootstrap emitter. Confirm the
     exact keys and values before passing it to the upstream unbounded parser.
     The maximum argv and envp counts leave space for all these items. */
  if (auxv[0] != AT_PHDR || auxv[1] != record->main_phdr
      || auxv[2] != AT_PHNUM || auxv[3] != record->main_phnum
      || auxv[4] != AT_PHENT || auxv[5] != sizeof (Elf64_Phdr)
      || auxv[6] != AT_ENTRY || auxv[7] != record->main_entry
      || auxv[8] != AT_BASE || auxv[9] != record->interpreter_base
      || auxv[10] != AT_PAGESZ || auxv[11] != 4096
      || auxv[12] != AT_SECURE || auxv[13] > 1
      || auxv[14] != AT_RANDOM || auxv[15] != (xos_u64) handoff->stack.random
      || auxv[16] != AT_NULL || auxv[17] != 0)
    return 0;
  *output = (struct xos_d1_entry_view) { argc, args, environment, auxv, record };
  return 1;
}
