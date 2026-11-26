/* SPDX-License-Identifier: Apache-2.0 */
/* Build with GNU's actual interpreter headers and compile flags. */
#include <ldsodefs.h>
#include <pthreadP.h>
#include <tls.h>
#include "xos_file_trap.h"
#include "xos_rtld_heap.h"
#include "xos_rtld_initial_tls.h"
#include "xos_thread_identity.h"

void *__minimal_malloc (size_t);
static struct link_map modules[2];
static struct link_map *initial_order[2];

static __attribute__ ((noreturn)) void
stop (const char *message, size_t size, int code)
{
  (void) file_trap (11, 1, (uintptr_t) message, size);
  (void) file_trap (2, code, 0, 0);
  __builtin_trap ();
}

#define CHECK(condition, reason)                            \
  do                                                        \
    {                                                       \
      if (!(condition))                                     \
        {                                                   \
          static const char m[] = "D1_CLOSURE_TLS_FAIL " reason "\n"; \
          stop (m, sizeof (m) - 1, 61);                      \
        }                                                   \
    }                                                       \
  while (0)

static void
add_module (struct link_map *map, uintptr_t bias)
{
  const Elf64_Ehdr *elf = (const void *) bias;
  const Elf64_Phdr *phdrs = (const void *) (bias + elf->e_phoff);
  const Elf64_Phdr *tls = NULL;
  for (size_t i = 0; i < elf->e_phnum; ++i)
    if (phdrs[i].p_type == PT_TLS)
      {
        CHECK (tls == NULL, "one PT_TLS per input");
        tls = &phdrs[i];
      }
  CHECK (tls != NULL && tls->p_filesz != 0 && tls->p_memsz > tls->p_filesz
         && tls->p_align != 0 && (tls->p_align & (tls->p_align - 1)) == 0,
         "linked TLS data and BSS");
  map->l_addr = bias;
  map->l_tls_align = tls->p_align;
  map->l_tls_blocksize = tls->p_memsz;
  map->l_tls_firstbyte_offset = tls->p_vaddr & (tls->p_align - 1);
  map->l_tls_initimage = (void *) (bias + tls->p_vaddr);
  map->l_tls_initimage_size = tls->p_filesz;
  _dl_assign_tls_modid (map);
}

void d1_run_closure_tls (uintptr_t, uintptr_t, int) __attribute__ ((noreturn));

void
d1_run_closure_tls (uintptr_t first, uintptr_t second, int exhausted)
{
  __rtld_malloc_init_stubs ();
  __tls_pre_init_tp ();
  add_module (&modules[0], first);
  add_module (&modules[1], second);
  CHECK (modules[0].l_tls_modid == 1 && modules[1].l_tls_modid == 2,
         "GNU assigned distinct module IDs");
  modules[0].l_next = &modules[1];
  modules[1].l_prev = &modules[0];
  GL (dl_ns)[LM_ID_BASE]._ns_loaded = &modules[0];
  GL (dl_ns)[LM_ID_BASE]._ns_nloaded = 2;
  initial_order[0] = &modules[0];
  initial_order[1] = &modules[1];
  modules[0].l_initfini = initial_order;
  modules[0].l_searchlist.r_nlist = 2;

  if (exhausted)
    {
      /* Two native pages. GNU consumes the first and fits one last small
         block in the second; no more space for the initial slot list. */
      CHECK (__minimal_malloc (XOS_VM_PAGE) != NULL
             && __minimal_malloc (XOS_VM_PAGE - 64) != NULL,
             "consume the qualified early heap budget");
    }
  struct pthread *pd = __xos_rtld_init_tls (0);
  CHECK (!exhausted && pd != NULL && THREAD_SELF == pd
         && __rtld_tls_init_tp_called, "GNU TCB installed by init_tls");
  struct xos_thread_info identity;
  CHECK (xos_thread_lifecycle (41, (uintptr_t) &identity, 0) == 0
         && identity.thread_pointer == (uintptr_t) pd
         && pd->tid == identity.tid, "native initial thread identity");
  dtv_t *dtv = THREAD_DTV ();
  CHECK (dtv != NULL && dtv == GL (dl_initial_dtv) && dtv[-1].counter >= 2
         && dtv[0].counter == 0, "original GNU DTV storage");

  __xos_rtld_init_tls_templates (&modules[0], pd);
  CHECK (dtv[0].counter == GL (dl_tls_generation) && dtv[0].counter == 1,
         "initial GNU DTV generation");
  void *previous = pd;
  const unsigned char first_bytes[] = { 0x51, 0xa7 };
  for (size_t j = 0; j < 2; ++j)
    {
      const struct link_map *map = &modules[j];
      const dtv_t *entry = &dtv[map->l_tls_modid];
      volatile unsigned char *storage = entry->pointer.val;
      CHECK (storage == (unsigned char *) pd - map->l_tls_offset
             && (void *) storage != previous && entry->pointer.to_free == NULL
             && (uintptr_t) storage % map->l_tls_align == map->l_tls_firstbyte_offset,
             "independent aligned TLS slots");
      CHECK (storage[0] == first_bytes[j] && storage[1] == 0x3c && storage[2] == 0x19,
             "actual pinned PT_TLS data");
      for (size_t i = map->l_tls_initimage_size; i < map->l_tls_blocksize; ++i)
        CHECK (storage[i] == 0, "zero TLS BSS");
      storage[0] = 0x70 + j;
      CHECK (*(const unsigned char *) map->l_tls_initimage == first_bytes[j],
             "mapped template remains independent");
      previous = entry->pointer.val;
    }

  CHECK (__xos_rtld_heap_seal () == 0
         && __xos_rtld_heap_grow (XOS_VM_PAGE) == XOS_RTLD_HEAP_FAILED,
         "initial TLS remains owned after heap seal");
  const long now = file_trap (46, 0, 0, 0);
  CHECK (now >= 0 && file_trap (47, now + 40000000, 0, 0) == 0
         && file_trap (46, 0, 0, 0) >= now + 40000000, "yield across native dispatch");
  CHECK (THREAD_SELF == pd && THREAD_DTV () == dtv
         && *(const unsigned char *) dtv[1].pointer.val == 0x70
         && *(const unsigned char *) dtv[2].pointer.val == 0x71,
         "resumed process owns initial TLS");

  static const char success[] = "D1_CLOSURE_TLS_OK modules=2 tdata=checked "
                               "tbss=zero dtv=1 tp=preserved\n";
  stop (success, sizeof (success) - 1, 0);
}
