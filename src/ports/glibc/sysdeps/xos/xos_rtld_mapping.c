/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "xos_rtld_mapping.h"
#include "xos_file_trap.h"

enum { pinned_read_at = 30, max_pins = 16, max_program_headers = 64 };
static struct xos_rtld_images *active;

int
__xos_rtld_attach_images (struct xos_rtld_images *images)
{
  if (active != 0)
    return EBUSY;
  if (images == 0 || images->files == 0 || images->pins == 0
      || images->count == 0 || images->count > max_pins
      || images->files->phase != xos_file_session_active || images->files->request_sequence == 0)
    return EINVAL;
  for (xos_u32 i = 0; i < images->count; ++i)
    {
      const struct xos_rtld_pin *pin = &images->pins[i];
      if (pin->fd < 0 || pin->handle == 0 || pin->inode == 0 || pin->inode > 65535
          || pin->file_bytes < sizeof (Elf64_Ehdr) || pin->file_bytes > 0xfffffffeU)
        return EINVAL;
      for (xos_u32 j = 0; j < i; ++j)
        if (images->pins[j].fd == pin->fd || images->pins[j].handle == pin->handle)
          return EINVAL;
    }
  active = images;
  return 0;
}

int
__xos_rtld_detach_images (struct xos_rtld_images *images)
{
  if (active == 0 || active != images)
    return EINVAL;
  active = 0;
  return 0;
}

static const struct xos_rtld_pin *
find_pin (int fd)
{
  if (active != 0)
    for (xos_u32 i = 0; i < active->count; ++i)
      if (active->pins[i].fd == fd)
        return &active->pins[i];
  return 0;
}

static long
pin_request (const struct xos_rtld_pin *pin, unsigned int operation,
             xos_u64 offset, xos_u32 count)
{
  struct xos_file_request *request = &active->request;
  request->operation = operation;
  request->handle = pin->handle;
  request->offset = offset;
  request->length = count;
  request->flags = request->reserved = request->name_length = 0;
  return __xos_file_session_call (active->files, request, &active->response);
}

static bool
read_pin (void *source, xos_u64 offset, unsigned char *destination, xos_u32 count)
{
  const struct xos_rtld_pin *pin = source;
  if (offset > pin->file_bytes || count > pin->file_bytes - offset)
    return false;
  for (xos_u32 read = 0; read < count;)
    {
      struct xos_file_response *response = &active->response;
      xos_u32 part = count - read;
      if (part > sizeof (response->data))
        part = sizeof (response->data);
      if (pin_request (pin, pinned_read_at, offset + read, part) != 0 || response->length == 0)
        return false;
      for (xos_u32 i = 0; i < response->length; ++i)
        destination[read + i] = response->data[i];
      read += response->length;
    }
  return true;
}

bool
__xos_rtld_read_pin (int fd, xos_u64 offset, void *destination, xos_u32 count)
{
  const struct xos_rtld_pin *pin = find_pin (fd);
  return pin != 0 && (destination != 0 || count == 0)
    && read_pin ((void *) pin, offset, destination, count);
}

static bool
same_header (const Elf64_Ehdr *first, const Elf64_Ehdr *second)
{
  const unsigned char *a = (const void *) first, *b = (const void *) second;
  for (unsigned int i = 0; i < sizeof (*first); ++i)
    if (a[i] != b[i])
      return false;
  return true;
}

static void __attribute__ ((noreturn))
mapping_failed_to_release (void)
{
  static const char error[] = "XOS rtld: cannot roll back mapped object\n";
  (void) file_trap (11, 2, (xos_u64) error, sizeof (error) - 1);
  (void) file_trap (2, 127, 0, 0);
  __builtin_trap ();
}

void
__xos_rtld_release_image (struct xos_image_allocation *allocation)
{
  if (xos_image_release (allocation) != 0)
    mapping_failed_to_release ();
}

int
__xos_rtld_map_fd (int fd, const Elf64_Ehdr *expected, xos_u64 expected_phdr,
                   xos_rtld_compare_phdr compare, void *iterator,
                   struct xos_rtld_mapped *output)
{
  const struct xos_rtld_pin *pin = find_pin (fd);
  if (pin == 0)
    return active != 0 ? EBADF : ENOTSUP;
  if (expected == 0 || compare == 0 || output == 0 || output->allocation.bytes != 0
      || output->allocation.start != 0)
    return EINVAL;

  /* A pin is already open. Check its retained identity through the same
     session before reading the exact header and segments of that instance. */
  const long stat = pin_request (pin, file_fstat, 0, 0);
  if (stat != 0)
    return -stat;
  if ((active->response.flags & 1) != 0 || active->response.reserved != pin->inode
      || active->response.value != pin->file_bytes)
    return ESTALE;
  Elf64_Ehdr header;
  if (!read_pin ((void *) pin, 0, (unsigned char *) &header, sizeof (header)))
    return EIO;
  if (!same_header (&header, expected) || header.e_type != ET_DYN || header.e_machine != EM_X86_64
      || header.e_ehsize != sizeof (header) || header.e_phentsize != sizeof (Elf64_Phdr)
      || header.e_phoff < sizeof (header) || header.e_phnum == 0
      || header.e_phnum > max_program_headers)
    return ENOEXEC;

  Elf64_Phdr phdrs[max_program_headers];
  const xos_u32 phdr_bytes = header.e_phnum * sizeof (Elf64_Phdr);
  if (!read_pin ((void *) pin, header.e_phoff, (unsigned char *) phdrs, phdr_bytes))
    return EIO;
  struct xos_image_segment loads[XOS_IMAGE_MAX_LOADS];
  xos_u32 count = 0;
  xos_u64 relative_phdr = 0;
  for (unsigned int i = 0; i < header.e_phnum; ++i)
    {
      const Elf64_Phdr *p = &phdrs[i];
      if (!compare (iterator, i, p))
        return ENOEXEC;
      if (p->p_type != PT_LOAD)
        continue;
      if (p->p_align > 1 && ((p->p_align & (p->p_align - 1)) != 0
          || p->p_vaddr % p->p_align != p->p_offset % p->p_align
          || pin->bias % p->p_align != 0))
        return ENOEXEC;
      if (p->p_filesz == 0 && p->p_memsz == 0)
        continue;
      loads[count++] = (struct xos_image_segment) { p->p_offset, p->p_vaddr,
        p->p_filesz, p->p_memsz, p->p_flags };
      if (header.e_phoff >= p->p_offset && phdr_bytes <= p->p_filesz
          && header.e_phoff - p->p_offset <= p->p_filesz - phdr_bytes
          && p->p_vaddr <= UINT64_MAX - (header.e_phoff - p->p_offset))
        relative_phdr = p->p_vaddr + (header.e_phoff - p->p_offset);
    }
  /* The deployed D1 subset supplies a mapped, file-backed table. Preserve
     elf/dl-load.c's convention of adjusting the relative PHDR after mapping. */
  if (relative_phdr == 0 || (expected_phdr != 0 && relative_phdr != expected_phdr))
    return ENOEXEC;
  const struct xos_image_mapping image = { pin->bias, header.e_entry, pin->file_bytes,
    pin->reservation_budget, pin->commit_budget, loads, count };
  struct xos_image_allocation allocation = { 0, 0 };
  const struct xos_image_map_result mapped = xos_image_map (&image, read_pin, (void *) pin, &allocation);
  if (mapped.rollback_error != 0)
    mapping_failed_to_release ();
  if (mapped.error == xos_image_map_layout)
    return ENOEXEC;
  if (mapped.error == xos_image_map_budget)
    return ENOMEM;
  if (mapped.error != xos_image_map_ok)
    return mapped.vm_error == -7 ? EEXIST : mapped.vm_error == -4 ? ENOMEM : EIO;
  *output = (struct xos_rtld_mapped) { allocation, pin->bias, relative_phdr };
  return 0;
}
