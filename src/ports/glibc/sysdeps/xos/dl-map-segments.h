/* SPDX-License-Identifier: Apache-2.0 */
#if IS_IN (rtld)
#include <errno.h>
#include "xos_rtld_mapping.h"

static bool
xos_compare_rtld_phdr (void *context, unsigned int index, const ElfW(Phdr) *pinned)
{
  const ElfW(Phdr) *scanned = _dl_pt_load_iterator_phdr_at (context, index);
  return scanned != NULL && memcmp (scanned, pinned, sizeof (*pinned)) == 0;
}

static const char *
_dl_map_segments (struct link_map *l, int fd, const ElfW(Ehdr) *header, int type,
                  struct dl_pt_load_iterator *it, size_t maplength, bool has_holes,
                  struct link_map *loader)
{
  (void) maplength;
  (void) has_holes;
  (void) loader;
  struct xos_rtld_mapped mapped = {0};
  int error = type != ET_DYN ? ENOTSUP
    : __xos_rtld_map_fd (fd, header, (uintptr_t) l->l_phdr, xos_compare_rtld_phdr, it, &mapped);
  if (error != 0)
    {
      __set_errno (error);
      return DL_MAP_SEGMENTS_ERROR_MAP_SEGMENT;
    }
  l->l_addr = mapped.bias;
  l->l_map_start = mapped.allocation.start;
  l->l_map_end = mapped.allocation.start + mapped.allocation.bytes;
  /* The inaccessible holes belong to this single reservation and are
     released in the same unmap as its committed pages. */
  l->l_contiguous = 1;
  l->l_phdr = (const void *) (uintptr_t) mapped.relative_phdr;
  return NULL;
}
#else
# include_next <dl-map-segments.h>
#endif
