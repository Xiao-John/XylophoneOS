/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_MAPPING_H
#define XOS_RTLD_MAPPING_H
#include <elf.h>
#include "xos_d1_start.h"
#include "xos_image_mapping.h"

#ifdef __cplusplus
extern "C" {
#endif

struct xos_rtld_lease
{
  xos_u64 cursor;
  unsigned int phase;
  int close_error;
};
struct xos_rtld_images
{
  struct xos_file_session *files;
  const struct xos_rtld_pin_plan *plan;
  struct xos_rtld_lease leases[2 * XOS_RTLD_MAX_PINS];
  struct xos_file_request request;
  struct xos_file_response response;
  struct xos_rtld_pin_plan retained_plan;
  long (*online_exchange) (const struct xos_file_request *, struct xos_file_response *, xos_u64);
  xos_u64 owner_pid, online_owner, online_deadline;
  unsigned int online_depth;
};

struct xos_rtld_mapped
{
  struct xos_image_allocation allocation;
  xos_u64 bias, relative_phdr;
};

typedef bool (*xos_rtld_compare_phdr) (void *, unsigned int, const Elf64_Phdr *);

/* Descriptors are private to the interpreter. The plan certifies already
   opened pins; the online profile retains its approved subset after startup.
   Attach, finish and mapping return zero or a positive errno value. */
int __xos_rtld_attach_images (struct xos_rtld_images *) __attribute__ ((visibility ("hidden")));
int __xos_rtld_attach_entry_images (void **, struct xos_rtld_images *, struct xos_d1_entry_view *)
  __attribute__ ((visibility ("hidden")));
/* Release startup-only pins and preserve the transport for libc handoff.
   Online approval pins survive until process exit. Error requires terminating
   startup to revoke remaining pins. */
int __xos_rtld_finish_images (struct xos_rtld_images *) __attribute__ ((visibility ("hidden")));
/* Private descriptor operations return a value or negative errno. */
int __xos_rtld_open_pin (const char *) __attribute__ ((visibility ("hidden")));
int __xos_rtld_open_pin_namespace (const char *, long) __attribute__ ((visibility ("hidden")));
int __xos_rtld_enable_online (long (*)(const struct xos_file_request *,
                            struct xos_file_response *, xos_u64))
  __attribute__ ((visibility ("hidden")));
/* GLIBC_PRIVATE, only the opt-in shared profile publishes these operations.
   A competing caller receives EBUSY, not an unbounded loader-lock wait. */
int __xos_rtld_online_begin (const char *, long, int, int);
void __xos_rtld_online_end (void);
long __xos_rtld_read_pin (int, void *, xos_u32) __attribute__ ((visibility ("hidden")));
long __xos_rtld_pread_pin (int, void *, xos_u32, xos_i64) __attribute__ ((visibility ("hidden")));
int __xos_rtld_stat_pin (int) __attribute__ ((visibility ("hidden")));
int __xos_rtld_close_pin (int) __attribute__ ((visibility ("hidden")));
int __xos_rtld_map_fd (int, const Elf64_Ehdr *, xos_u64, xos_rtld_compare_phdr, void *,
                       struct xos_rtld_mapped *) __attribute__ ((visibility ("hidden")));
void __xos_rtld_release_image (struct xos_image_allocation *) __attribute__ ((visibility ("hidden")));

#ifdef __cplusplus
}
#endif
#endif
