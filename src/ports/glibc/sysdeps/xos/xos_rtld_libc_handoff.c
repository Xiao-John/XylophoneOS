/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <ldsodefs.h>
#include <dl-hash.h>
#include <dl-new-hash.h>
#include <startup.h>
#include "xos_rtld_heap.h"
#include "xos_rtld_libc_handoff.h"
#include "xos_rtld_sysdep_start.h"

int
__xos_rtld_handoff_libc_files (struct link_map *libc_map,
                               struct xos_rtld_images *images)
{
  if (images == NULL || images->files == NULL || images->plan == NULL)
    return EINVAL;
  const int closed = __xos_rtld_finish_images (images);
  if (closed != 0)
    return closed;
  if (libc_map == NULL || !libc_map->l_relocated || libc_map->l_versyms == NULL
      || libc_map->l_versions == NULL)
    return ENOEXEC;

  static const char name[] = "__xos_file_adopt_startup";
  static const char version[] = "GLIBC_PRIVATE";
  const ElfW(Sym) *symbol = _dl_lookup_direct (libc_map, name, _dl_new_hash (name),
                                              version, _dl_elf_hash (version));
  if (symbol == NULL || ELFW (ST_TYPE) (symbol->st_info) != STT_FUNC)
    return ENOEXEC;

  xos_file_startup_receiver adopt = DL_SYMBOL_ADDRESS (libc_map, symbol);
  const long result = adopt (images->files, images->plan->deadline_ns);
  return (int) -result;
}

void
_dl_sysdep_start_cleanup (void)
{
  /* GNU calls this after libc relocation and the allocator switch. No
     constructors or program code can observe the late G3 table yet. */
  if (!__rtld_malloc_is_complete ())
    _startup_fatal ("XOS rtld: shared libc allocator is unavailable\n");
  if (__xos_rtld_handoff_libc_files (GL (dl_ns)[LM_ID_BASE].libc_map,
                                    &__xos_rtld_start_images) != 0)
    _startup_fatal ("XOS rtld: cannot hand off native file startup\n");
  if (__xos_rtld_heap_seal () != 0)
    _startup_fatal ("XOS rtld: cannot seal the early startup heap\n");
}
