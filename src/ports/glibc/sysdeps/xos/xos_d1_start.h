/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_D1_START_H
#define XOS_GLIBC_D1_START_H
#include "xos_file_session.h"
#include "xos_rtld_pin_plan.h"
#include "xos_rtld_heap_plan.h"

#define XOS_D1_MAX_ARGS 64
#define XOS_D1_MAX_ENVIRONMENT 64
#define XOS_D1_AUX_ITEMS 9
#define XOS_D1_ENTRY_WORDS (1 + XOS_D1_MAX_ARGS + 1 + XOS_D1_MAX_ENVIRONMENT + 1 + 2 * XOS_D1_AUX_ITEMS)
#define XOS_D1_STACK_BOTTOM 0x7ffdc000ULL
/* Leave half of the native 128 KiB stack below the initial interpreter %rsp.
   The first call and the rest of startup grow downward from this address. */
#define XOS_D1_STACK_GROWTH_BYTES (64ULL * 1024)
#define XOS_D1_STACK_ENTRY_MIN (XOS_D1_STACK_BOTTOM + XOS_D1_STACK_GROWTH_BYTES)
#define XOS_D1_STARTUP_BEGIN 0x7fffc000ULL
#define XOS_D1_STACK_TOP 0x80000000ULL
#define XOS_D1_ENTRY_MAGIC 0x3152544e45444f58ULL
#define XOS_D1_ENTRY_VERSION 3

struct __attribute__ ((aligned (16))) xos_d1_entry_stack
{
  xos_u64 words[XOS_D1_ENTRY_WORDS];
  unsigned char random[16];
};

/* Private same-process handoff at a fixed distance above the original %rsp.
   It is outside argv/envp/auxv, across the downward-growing interpreter stack.
   It describes startup ownership without granting file or address-space rights. */
struct xos_d1_entry_record
{
  xos_u64 magic;
  xos_u32 version, size;
  xos_u64 main_phdr, main_phnum, main_entry, interpreter_base, interpreter_entry;
  struct xos_file_session files;
  struct xos_rtld_pin_plan dependencies;
  struct xos_rtld_heap_plan heap;
};

struct xos_d1_entry_handoff
{
  struct xos_d1_entry_stack stack;
  struct xos_d1_entry_record record;
};

struct xos_d1_entry_view
{
  xos_u64 argc;
  xos_u64 *argv, *environment, *auxv;
  struct xos_d1_entry_record *record;
};

#ifdef __cplusplus
extern "C" {
#endif
/* For the post-self-relocation rtld path. Only the validated bounded view is
   returned. The caller still must adopt the session before early file I/O. */
int __xos_rtld_check_entry (void **, struct xos_d1_entry_view *)
  __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
