/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_PIN_PLAN_H
#define XOS_RTLD_PIN_PLAN_H
#include "xos_wait_word.h"

enum { XOS_RTLD_MAX_PINS = 16, XOS_RTLD_MAX_SONAME = 128 };

/* Supplied by the already verified dependency closure. The bootstrap owns
   each existing read-only pin until it publishes this private plan. */
struct xos_rtld_pin
{
  int fd;
  xos_u32 handle, inode;
  xos_u64 file_bytes, bias, reservation_budget, commit_budget;
  char soname[XOS_RTLD_MAX_SONAME];
};

struct xos_rtld_pin_plan
{
  xos_u64 deadline_ns;
  xos_u32 count, reserved;
  struct xos_rtld_pin pins[XOS_RTLD_MAX_PINS];
  xos_u32 online_version, online_mask, isolated_mask, online_reserved;
};

static inline unsigned int
xos_rtld_soname_length (const char *name)
{
  if (name == 0 || name[0] == 0)
    return 0;
  for (unsigned int i = 0; i < XOS_RTLD_MAX_SONAME; ++i)
    {
      unsigned char c = name[i];
      if (c == 0)
        {
          if (name[0] == '.' && (i == 1 || (i == 2 && name[1] == '.')))
            return 0;
          return i;
        }
      if (c == '/' || c < 0x20 || c == 0x7f)
        return 0;
    }
  return 0;
}

static inline int
xos_rtld_same_soname (const char *first, const char *second)
{
  for (unsigned int i = 0; i < XOS_RTLD_MAX_SONAME; ++i)
    {
      if (first[i] != second[i])
        return 0;
      if (first[i] == 0)
        return 1;
    }
  return 0;
}

static inline int
xos_rtld_valid_pin_plan (const struct xos_rtld_pin_plan *plan)
{
  if (plan == 0 || plan->count > XOS_RTLD_MAX_PINS || plan->reserved != 0)
    return 0;
  if (plan->online_reserved != 0 || (plan->online_mask >> plan->count)
      || (plan->isolated_mask & ~plan->online_mask)
      || (plan->online_mask ? plan->online_version != 1
                            : plan->online_version != 0 || plan->isolated_mask != 0))
    return 0;
  /* A closure without pins has no file request to constrain.  */
  if (plan->count == 0)
    return plan->deadline_ns == 0;
  if (plan->deadline_ns == 0 || plan->deadline_ns > __INT64_MAX__)
    return 0;
  for (xos_u32 i = 0; i < plan->count; ++i)
    {
      const struct xos_rtld_pin *pin = &plan->pins[i];
      if (pin->fd < 0 || pin->handle == 0 || pin->inode == 0 || pin->inode > 65535
          || (plan->online_mask != 0 && pin->fd > __INT_MAX__ - 32)
          || pin->file_bytes < 64 || pin->file_bytes > 0xfffffffeU
          || pin->reservation_budget == 0 || pin->commit_budget == 0
          || !xos_rtld_soname_length (pin->soname))
        return 0;
      for (xos_u32 j = 0; j < i; ++j)
        if (plan->pins[j].fd == pin->fd || plan->pins[j].handle == pin->handle
            || (plan->online_mask != 0
                && (plan->pins[j].fd + 32 == pin->fd || pin->fd + 32 == plan->pins[j].fd))
            || plan->pins[j].inode == pin->inode
            || xos_rtld_same_soname (plan->pins[j].soname, pin->soname))
          return 0;
    }
  return 1;
}
#endif
