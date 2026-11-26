/* SPDX-License-Identifier: Apache-2.0
   Native LOAD copy/protect shared by the bootstrap SDK and the GNU rtld.
   It performs no file discovery, relocation or TLS-dependent operation. */
#ifndef XOS_IMAGE_MAPPING_H
#define XOS_IMAGE_MAPPING_H
#include <stdbool.h>
#include "xos_vm_native.h"

enum { XOS_IMAGE_MAX_LOADS = 64, XOS_IMAGE_MAX_PAGES = 65536,
       XOS_VM_MAX_CHANGE_PAGES = 4096 };
enum xos_image_map_error
{
  xos_image_map_ok, xos_image_map_layout, xos_image_map_budget,
  xos_image_map_reserve, xos_image_map_commit, xos_image_map_read,
  xos_image_map_protect
};
struct xos_image_segment
{
  uint64_t offset, address, file_bytes, memory_bytes;
  uint32_t permissions; /* ELF PF_R, PF_W, PF_X. */
};
struct xos_image_allocation { uint64_t start, bytes; };
struct xos_image_mapping
{
  uint64_t bias, entry, file_bytes, reservation_budget, commit_budget;
  const struct xos_image_segment *loads;
  uint32_t load_count;
};
struct xos_image_map_result
{
  enum xos_image_map_error error;
  int64_t vm_error, rollback_error;
};
typedef bool (*xos_image_reader) (void *, uint64_t, unsigned char *, uint32_t);

static inline uint64_t
xos_image_page_start (uint64_t address)
{
  return address & -(uint64_t) XOS_VM_PAGE;
}

static inline uint64_t
xos_image_page_end (uint64_t address)
{
  return xos_image_page_start (address + XOS_VM_PAGE - 1);
}

static inline uint32_t
xos_image_protection (uint32_t permissions)
{
  switch (permissions)
    {
    case 4: return 1; /* R */
    case 6: return 3; /* RW */
    case 5: return 5; /* RX */
    default: return 0;
    }
}

static inline enum xos_image_map_error
xos_image_plan (const struct xos_image_mapping *image,
                struct xos_image_allocation *range)
{
  if (image->bias < XOS_VM_BEGIN || image->bias >= XOS_VM_END
      || image->bias % XOS_VM_PAGE != 0 || image->loads == 0
      || image->load_count == 0 || image->load_count > XOS_IMAGE_MAX_LOADS)
    return xos_image_map_layout;
  if (image->reservation_budget == 0 || image->commit_budget == 0)
    return xos_image_map_budget;

  const uint64_t limit = XOS_VM_END - image->bias;
  uint64_t begin = 0, end = 0, committed = 0;
  bool has_entry = image->entry == 0;  /* A DSO need not have an entry. */
  for (uint32_t i = 0; i < image->load_count; ++i)
    {
      const struct xos_image_segment *load = &image->loads[i];
      if (load->address >= limit || load->memory_bytes == 0
          || load->memory_bytes > limit - load->address
          || load->file_bytes > load->memory_bytes || load->offset > image->file_bytes
          || load->file_bytes > image->file_bytes - load->offset
          || load->address % XOS_VM_PAGE != load->offset % XOS_VM_PAGE
          || xos_image_protection (load->permissions) == 0)
        return xos_image_map_layout;
      const uint64_t first = xos_image_page_start (load->address);
      if (i == 0)
        begin = first;
      else if (first < end)
        return xos_image_map_layout;
      end = xos_image_page_end (load->address + load->memory_bytes);
      committed += end - first;
      if (end - begin > image->reservation_budget
          || end - begin > (uint64_t) XOS_IMAGE_MAX_PAGES * XOS_VM_PAGE
          || committed > image->commit_budget)
        return xos_image_map_budget;
      if ((load->permissions & 1) != 0 && image->entry >= load->address
          && image->entry - load->address < load->file_bytes)
        has_entry = true;
    }
  if (!has_entry)
    return xos_image_map_layout;
  range->start = image->bias + begin;
  range->bytes = end - begin;
  return xos_image_map_ok;
}

static inline int64_t
xos_image_vm (uint32_t operation, uint32_t flags, uint64_t address,
              uint64_t bytes, uint64_t alignment, uint32_t protection)
{
  const struct xos_vm_request r = { 1, sizeof (r), operation, flags,
                                    address, bytes, alignment, protection, 0, 0, 0 };
  return xos_vm_call (&r);
}

static inline int64_t
xos_image_release (struct xos_image_allocation *range)
{
  if (range->bytes == 0)
    return range->start == 0 ? 0 : -1;
  int64_t code = xos_image_vm (XOS_VM_UNMAP, 0, range->start, range->bytes, 0, 0);
  const uint64_t maximum = (uint64_t) XOS_VM_MAX_CHANGE_PAGES * XOS_VM_PAGE;
  if (code == XOS_VM_RESOURCES && range->bytes > maximum)
    {
      /* The native whole-range transaction can enumerate 4096 committed
         pages. Decommit in bounded transactions while keeping the entire
         reservation owned, then remove the now-empty reservation at once. */
      for (uint64_t done = 0; done < range->bytes;)
        {
          const uint64_t remaining = range->bytes - done;
          const uint64_t batch = remaining < maximum ? remaining : maximum;
          code = xos_image_vm (XOS_VM_DECOMMIT, 0, range->start + done, batch, 0, 0);
          if (code != 0)
            return code;
          done += batch;
        }
      code = xos_image_vm (XOS_VM_UNMAP, 0, range->start, range->bytes, 0, 0);
    }
  if (code == 0)
    range->start = range->bytes = 0;
  return code;
}

static inline int64_t
xos_image_change_load (uint32_t operation, uint64_t bias,
                       const struct xos_image_segment *load, uint32_t protection)
{
  const uint64_t start = bias + xos_image_page_start (load->address);
  const uint64_t end = bias + xos_image_page_end (load->address + load->memory_bytes);
  const uint64_t maximum = (uint64_t) XOS_VM_MAX_CHANGE_PAGES * XOS_VM_PAGE;
  for (uint64_t at = start; at < end;)
    {
      const uint64_t batch = end - at < maximum ? end - at : maximum;
      const int64_t code = xos_image_vm (operation, 0, at, batch, 0, protection);
      if (code != 0)
        return code;
      at += batch;
    }
  return 0;
}

static inline struct xos_image_map_result
xos_image_rollback (enum xos_image_map_error error, int64_t vm_error,
                    struct xos_image_allocation *range)
{
  const struct xos_image_map_result result = { error, vm_error, xos_image_release (range) };
  return result;
}

static inline struct xos_image_map_result
xos_image_map (const struct xos_image_mapping *image, xos_image_reader read, void *source,
               struct xos_image_allocation *allocation)
{
  struct xos_image_allocation range = { 0, 0 };
  struct xos_image_map_result result = { xos_image_map_layout, 0, 0 };
  if (read == 0 || allocation->start != 0 || allocation->bytes != 0)
    return result;
  result.error = xos_image_plan (image, &range);
  if (result.error != xos_image_map_ok)
    return result;
  const int64_t reserved = xos_image_vm (XOS_VM_RESERVE, XOS_VM_EXACT, range.start,
                                         range.bytes, XOS_VM_PAGE, 0);
  if (reserved < 0)
    {
      result.error = xos_image_map_reserve;
      result.vm_error = reserved;
      return result;
    }
  if ((uint64_t) reserved != range.start)
    {
      range.start = reserved;
      return xos_image_rollback (xos_image_map_reserve, -2, &range);
    }

  for (uint32_t i = 0; i < image->load_count; ++i)
    {
      const struct xos_image_segment *load = &image->loads[i];
      const int64_t code = xos_image_change_load (XOS_VM_COMMIT, image->bias, load, 3);
      if (code != 0)
        return xos_image_rollback (xos_image_map_commit, code, &range);
      /* New native pages are zeroed. Only byte ranges named by LOAD are read. */
      if (load->file_bytes != 0
          && !read (source, load->offset, (unsigned char *) (image->bias + load->address),
                    (uint32_t) load->file_bytes))
        return xos_image_rollback (xos_image_map_read, 0, &range);
    }
  for (uint32_t i = 0; i < image->load_count; ++i)
    {
      const struct xos_image_segment *load = &image->loads[i];
      const uint32_t access = xos_image_protection (load->permissions);
      if (access == 3)
        continue;
      const int64_t code = xos_image_change_load (XOS_VM_PROTECT, image->bias, load, access);
      if (code != 0)
        return xos_image_rollback (xos_image_map_protect, code, &range);
    }
  *allocation = range;
  return result;
}
#endif
