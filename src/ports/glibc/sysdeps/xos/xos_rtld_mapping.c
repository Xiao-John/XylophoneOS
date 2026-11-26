/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "xos_rtld_mapping.h"
#include "xos_rtld_heap.h"
#include "xos_file_trap.h"

enum { pinned_close = 8, pinned_read_at = 30, max_program_headers = 64 };
enum { available, leased, closed };
static struct xos_rtld_images *active;

static int
phase_error (const struct xos_rtld_images *images)
{
  if (images == 0)
    return ENOTSUP;
  if (images->files->phase != xos_file_session_active)
    return EIO;
  if (images->plan->count == 0)
    return 0;
  const long now = file_trap (46, 0, 0, 0);
  if (now < 0)
    return EIO;
  return (xos_u64) now >= images->plan->deadline_ns ? ETIMEDOUT : 0;
}

int
__xos_rtld_attach_images (struct xos_rtld_images *images)
{
  if (active != 0)
    return EBUSY;
  if (images == 0 || images->files == 0 || !xos_rtld_valid_pin_plan (images->plan)
      || images->files->owner_pid == 0 || images->files->request_sequence == 0)
    return EINVAL;
  const int error = phase_error (images);
  if (error != 0)
    return error;
  const long pid = file_trap (6, 0, 0, 0);
  xos_u32 handles[2] = { 0, 0 };
  if (pid <= 0 || images->files->owner_pid != (xos_u64) pid
      || file_trap (22, (xos_u64) handles, 0, 0) != 0
      || handles[0] == 0 || handles[1] == 0 || handles[0] == handles[1]
      || handles[0] != images->files->send_handle || handles[1] != images->files->receive_handle)
    return EIO;
  for (xos_u32 i = 0; i < images->plan->count; ++i)
    images->leases[i] = (struct xos_rtld_lease) { 0, available, 0 };
  active = images;
  return 0;
}

int
__xos_rtld_attach_entry_images (void **stack, struct xos_rtld_images *images,
                                struct xos_d1_entry_view *output)
{
  struct xos_d1_entry_view view;
  if (images == 0 || output == 0 || !__xos_rtld_check_entry (stack, &view))
    return EINVAL;
  if (active != 0)
    return EBUSY;
  images->files = &view.record->files;
  images->plan = &view.record->dependencies;
  int error = __xos_rtld_attach_images (images);
  if (error == 0 && view.record->heap.bytes != 0)
    {
      error = __xos_rtld_heap_begin (&view.record->heap);
      if (error != 0)
        (void) __xos_rtld_finish_images (images);
    }
  if (error == 0)
    *output = view;
  return error;
}

static int
find_lease (int fd)
{
  for (xos_u32 i = 0; i < active->plan->count; ++i)
    if (active->plan->pins[i].fd == fd && active->leases[i].phase == leased)
      return i;
  return -1;
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
  return __xos_file_session_call_until (active->files, request, &active->response,
                                        active->plan->deadline_ns);
}

static int
close_lease (unsigned int index)
{
  struct xos_rtld_lease *lease = &active->leases[index];
  if (lease->phase == closed)
    return lease->close_error;
  lease->phase = closed;
  /* Upstream may try a second close while unwinding. Never replay the
     first close if its delivery or response was uncertain. */
  lease->close_error = pin_request (&active->plan->pins[index], pinned_close, 0, 0);
  return lease->close_error;
}

int
__xos_rtld_finish_images (struct xos_rtld_images *images)
{
  if (images == 0 || active != images)
    return EINVAL;
  int first_error = phase_error (images);
  for (xos_u32 i = 0; i < images->plan->count; ++i)
    {
      const int error = close_lease (i);
      if (first_error == 0 && error != 0)
        first_error = -error;
    }
  active = 0;
  return first_error;
}

int
__xos_rtld_open_pin (const char *name)
{
  const int error = phase_error (active);
  if (error != 0)
    return -error;
  if (!xos_rtld_soname_length (name))
    return -EINVAL;
  for (xos_u32 i = 0; i < active->plan->count; ++i)
    {
      const struct xos_rtld_pin *pin = &active->plan->pins[i];
      if (xos_rtld_same_soname (pin->soname, name))
        {
          if (active->leases[i].phase != available)
            return -EALREADY;
          active->leases[i].phase = leased;
          return pin->fd;
        }
    }
  return -ENOENT;
}

static long
read_pin (const struct xos_rtld_pin *pin, xos_u64 offset, void *buffer, xos_u32 count)
{
  if (buffer == 0 && count != 0)
    return -EFAULT;
  if (offset >= pin->file_bytes)
    return 0;
  if (count > pin->file_bytes - offset)
    count = pin->file_bytes - offset;
  unsigned char *destination = buffer;
  xos_u32 done = 0;
  while (done < count)
    {
      struct xos_file_response *response = &active->response;
      xos_u32 part = count - done;
      if (part > sizeof (response->data))
        part = sizeof (response->data);
      const long result = pin_request (pin, pinned_read_at, offset + done, part);
      if (result != 0)
        return result;
      if (response->length == 0)
        return -EIO; /* EOF inside the pinned instance's confirmed extent. */
      for (xos_u32 i = 0; i < response->length; ++i)
        destination[done + i] = response->data[i];
      done += response->length;
    }
  return done;
}

struct pin_reader
{
  const struct xos_rtld_pin *pin;
  int error;
};

static bool
read_exact (void *source, xos_u64 offset, unsigned char *buffer, xos_u32 count)
{
  struct pin_reader *reader = source;
  const long got = read_pin (reader->pin, offset, buffer, count);
  if (got == count)
    return true;
  reader->error = got < 0 ? -got : EIO;
  return false;
}

long
__xos_rtld_pread_pin (int fd, void *buffer, xos_u32 count, xos_i64 offset)
{
  const int error = phase_error (active);
  if (error != 0)
    return -error;
  const int index = find_lease (fd);
  if (index < 0)
    return -EBADF;
  if (offset < 0)
    return -EINVAL;
  return read_pin (&active->plan->pins[index], offset, buffer, count);
}

long
__xos_rtld_read_pin (int fd, void *buffer, xos_u32 count)
{
  const int error = phase_error (active);
  if (error != 0)
    return -error;
  const int index = find_lease (fd);
  if (index < 0)
    return -EBADF;
  struct xos_rtld_lease *lease = &active->leases[index];
  const long got = read_pin (&active->plan->pins[index], lease->cursor, buffer, count);
  if (got > 0)
    lease->cursor += got;
  return got;
}

static int
stat_pin (const struct xos_rtld_pin *pin)
{
  const long stat = pin_request (pin, file_fstat, 0, 0);
  if (stat != 0)
    return stat;
  if ((active->response.flags & 1) != 0 || active->response.reserved != pin->inode
      || active->response.value != pin->file_bytes)
    return -ESTALE;
  return 0;
}

int
__xos_rtld_stat_pin (int fd)
{
  const int error = phase_error (active);
  if (error != 0)
    return -error;
  const int index = find_lease (fd);
  return index < 0 ? -EBADF : stat_pin (&active->plan->pins[index]);
}

int
__xos_rtld_close_pin (int fd)
{
  if (active == 0)
    return -ENOTSUP;
  const int index = find_lease (fd);
  return index < 0 ? -EBADF : close_lease (index);
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
  const int error = phase_error (active);
  if (error != 0)
    return error;
  const int index = find_lease (fd);
  if (index < 0)
    return EBADF;
  const struct xos_rtld_pin *pin = &active->plan->pins[index];
  if (expected == 0 || compare == 0 || output == 0 || output->allocation.bytes != 0
      || output->allocation.start != 0)
    return EINVAL;

  /* A pin is already open. Check its retained identity through the same
     session before reading the exact header and segments of that instance. */
  const int stat = stat_pin (pin);
  if (stat != 0)
    return -stat;
  Elf64_Ehdr header;
  const long header_read = read_pin (pin, 0, &header, sizeof (header));
  if (header_read != sizeof (header))
    return header_read < 0 ? -header_read : EIO;
  if (!same_header (&header, expected) || header.e_type != ET_DYN || header.e_machine != EM_X86_64
      || header.e_ehsize != sizeof (header) || header.e_phentsize != sizeof (Elf64_Phdr)
      || header.e_phoff < sizeof (header) || header.e_phnum == 0
      || header.e_phnum > max_program_headers)
    return ENOEXEC;

  Elf64_Phdr phdrs[max_program_headers];
  const xos_u32 phdr_bytes = header.e_phnum * sizeof (Elf64_Phdr);
  const long table_read = read_pin (pin, header.e_phoff, phdrs, phdr_bytes);
  if (table_read != phdr_bytes)
    return table_read < 0 ? -table_read : EIO;
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
  struct pin_reader reader = { pin, 0 };
  const struct xos_image_map_result mapped = xos_image_map (&image, read_exact, &reader, &allocation);
  if (mapped.rollback_error != 0)
    mapping_failed_to_release ();
  if (mapped.error == xos_image_map_layout)
    return ENOEXEC;
  if (mapped.error == xos_image_map_budget)
    return ENOMEM;
  if (mapped.error == xos_image_map_read)
    return reader.error;
  if (mapped.error != xos_image_map_ok)
    return mapped.vm_error == -7 ? EEXIST : mapped.vm_error == -4 ? ENOMEM : EIO;
  const int finished = phase_error (active);
  if (finished != 0)
    {
      __xos_rtld_release_image (&allocation);
      return finished;
    }
  *output = (struct xos_rtld_mapped) { allocation, pin->bias, relative_phdr };
  return 0;
}
