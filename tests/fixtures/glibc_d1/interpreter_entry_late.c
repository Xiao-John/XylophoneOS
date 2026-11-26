/* SPDX-License-Identifier: Apache-2.0 */
#include <elf.h>
#include <stdio.h>
#include <string.h>
#include <sys/auxv.h>
#include <unistd.h>
#include "xos_d1_start.h"
#include "xos_file_runtime.h"

extern const struct xos_d1_entry_view *d1_entry_view (void);
extern xos_u32 d1_entry_sequence (void);
extern int d1_release_images (void);
extern int d1_early_heap_still_live (void);
extern void _dl_aux_init (Elf64_auxv_t *);
extern Elf64_auxv_t *_dl_auxv;

int
main (void)
{
  const struct xos_d1_entry_view *view = d1_entry_view ();
  Elf64_auxv_t *original = _dl_auxv;
  _dl_aux_init ((Elf64_auxv_t *) view->auxv);
  int headers = getauxval (AT_PHDR) == view->record->main_phdr
    && getauxval (AT_PHNUM) == view->record->main_phnum
    && getauxval (AT_ENTRY) == view->record->main_entry
    && getauxval (AT_BASE) == view->record->interpreter_base;
  _dl_aux_init (original);
  if (!headers || !d1_release_images () || !d1_early_heap_still_live ())
    return 41;

  char data[4];
  struct xos_file_request request = { .operation = 1 };
  struct xos_file_response response;
  if (read (0, data, sizeof (data)) != sizeof (data) || memcmp (data, "EFGH", sizeof (data)) != 0
      || __xos_file_exchange (&request, &response) != 0
      || response.request_id != d1_entry_sequence () + 2 || close (0) != 0)
    return 42;
  printf ("D1_INTERPRETER_ENTRY_PREPARED phdr=%lu interpreter=%p early=%u late=%u inherited=EFGH early_heap=live\n",
          (unsigned long) view->record->main_phnum, (void *) view->record->interpreter_entry,
          d1_entry_sequence (), response.request_id);
  return 0;
}
