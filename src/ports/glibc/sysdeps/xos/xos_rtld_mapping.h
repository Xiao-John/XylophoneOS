/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_MAPPING_H
#define XOS_RTLD_MAPPING_H
#include <elf.h>
#include "xos_file_session.h"
#include "xos_image_mapping.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The verified startup closure records these against its still-open pins.
   fd is the exact private loader descriptor that supplied its ELF headers.
   handle is the authenticated native pin. No path is opened by this backend. */
struct xos_rtld_pin
{
  int fd;
  xos_u32 handle, inode;
  xos_u64 file_bytes, bias, reservation_budget, commit_budget;
};

struct xos_rtld_images
{
  struct xos_file_session *files;
  const struct xos_rtld_pin *pins;
  xos_u32 count;
  struct xos_file_request request;
  struct xos_file_response response;
};

struct xos_rtld_mapped
{
  struct xos_image_allocation allocation;
  xos_u64 bias, relative_phdr;
};

typedef bool (*xos_rtld_compare_phdr) (void *, unsigned int, const Elf64_Phdr *);

/* State and its records remain alive and unchanged during the single-owner
   startup phase. The provider owns the pins, validates the aggregate budget
   and routes the loader descriptors to those same pins. detach never closes
   the inherited objects or resets the borrowed files session. */
int __xos_rtld_attach_images (struct xos_rtld_images *) __attribute__ ((visibility ("hidden")));
int __xos_rtld_detach_images (struct xos_rtld_images *) __attribute__ ((visibility ("hidden")));
bool __xos_rtld_read_pin (int, xos_u64, void *, xos_u32) __attribute__ ((visibility ("hidden")));
int __xos_rtld_map_fd (int, const Elf64_Ehdr *, xos_u64, xos_rtld_compare_phdr, void *,
                       struct xos_rtld_mapped *) __attribute__ ((visibility ("hidden")));
void __xos_rtld_release_image (struct xos_image_allocation *) __attribute__ ((visibility ("hidden")));

#ifdef __cplusplus
}
#endif
#endif
