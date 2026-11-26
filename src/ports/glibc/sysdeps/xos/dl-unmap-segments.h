/* SPDX-License-Identifier: Apache-2.0 */
#if IS_IN (rtld)
# ifndef XOS_RTLD_UNMAP_SEGMENTS_H
# define XOS_RTLD_UNMAP_SEGMENTS_H
#include <link.h>
#include "xos_rtld_mapping.h"

static inline void
_dl_unmap_segments (struct link_map *l)
{
  struct xos_image_allocation span =
    { l->l_map_start, l->l_map_end - l->l_map_start };
  __xos_rtld_release_image (&span);
}
# endif
#else
# include_next <dl-unmap-segments.h>
#endif
