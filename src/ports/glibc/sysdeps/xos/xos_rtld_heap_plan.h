/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_HEAP_PLAN_H
#define XOS_RTLD_HEAP_PLAN_H
#include "xos_image_mapping.h"

/* Exact native anonymous reservation owned by the verified startup. Its
   extent is both the reservation and the maximum committed heap budget. */
struct xos_rtld_heap_plan
{
  uint64_t base, bytes, deadline_ns;
};

static inline bool
xos_rtld_heap_plan_valid (const struct xos_rtld_heap_plan *plan)
{
  return plan != 0 && plan->deadline_ns != 0 && plan->deadline_ns <= __INT64_MAX__
    && plan->base >= XOS_VM_BEGIN && plan->base < XOS_VM_END
    && plan->base % XOS_VM_PAGE == 0 && plan->bytes != 0
    && plan->bytes % XOS_VM_PAGE == 0 && plan->bytes <= XOS_VM_END - plan->base
    && plan->bytes <= (uint64_t) XOS_IMAGE_MAX_PAGES * XOS_VM_PAGE;
}
#endif
