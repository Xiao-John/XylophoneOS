/* SPDX-License-Identifier: Apache-2.0 */
/* Build with the GNU interpreter's actual headers and compile flags. */
#include <ldsodefs.h>
#include <pthreadP.h>
#include <tls.h>
#include "get-dynamic-info.h"
#include "xos_file_trap.h"
#include "xos_rtld_heap.h"
#include "xos_rtld_initial_tls.h"

static struct link_map maps[2];
static struct link_map *startup_maps[] = { &maps[0], &maps[1] };
static struct r_scope_elem scope = { .r_list = startup_maps, .r_nlist = 2 };
static char provider_name[] = "libie_base.so";
static char consumer_name[] = "libie_use.so";

static __attribute__ ((noreturn)) void
stop (const char *message, size_t size, int code)
{
  (void) file_trap (11, 1, (uintptr_t) message, size);
  (void) file_trap (2, code, 0, 0);
  __builtin_trap ();
}

#define CHECK(condition, reason)                              \
  do                                                          \
    {                                                         \
      if (!(condition))                                       \
        {                                                     \
          static const char m[] = "D1_GNU_RELOC_FAIL " reason "\n"; \
          stop (m, sizeof (m) - 1, 63);                        \
        }                                                     \
    }                                                         \
  while (0)

static void
add_module (struct link_map *map, uintptr_t bias, char *name)
{
  const Elf64_Ehdr *elf = (const void *) bias;
  map->l_addr = bias;
  map->l_map_start = bias;
  map->l_name = name;
  map->l_real = map;
  map->l_type = lt_library;
  map->l_global = 1;
  map->l_phdr = (const void *) (bias + elf->e_phoff);
  map->l_phnum = elf->e_phnum;
  map->l_entry = bias + elf->e_entry;
  map->l_scope = map->l_scope_mem;
  map->l_scope_max = sizeof (map->l_scope_mem) / sizeof (*map->l_scope_mem);
  map->l_scope[0] = &scope;
  map->l_local_scope[0] = &scope;
  for (size_t i = 0; i < map->l_phnum; ++i)
    {
      const Elf64_Phdr *h = &map->l_phdr[i];
      switch (h->p_type)
        {
        case PT_LOAD:
          if (bias + h->p_vaddr + h->p_memsz > map->l_map_end)
            map->l_map_end = bias + h->p_vaddr + h->p_memsz;
          break;
        case PT_DYNAMIC:
          map->l_ld = (void *) (bias + h->p_vaddr);
          map->l_ld_readonly = !(h->p_flags & PF_W);
          break;
        case PT_TLS:
          CHECK (h->p_filesz != 0 && h->p_memsz > h->p_filesz && h->p_align != 0,
                 "ordinary initial-exec TLS template");
          map->l_tls_align = h->p_align;
          map->l_tls_blocksize = h->p_memsz;
          map->l_tls_firstbyte_offset = h->p_vaddr & (h->p_align - 1);
          map->l_tls_initimage = (void *) (bias + h->p_vaddr);
          map->l_tls_initimage_size = h->p_filesz;
          break;
        case PT_GNU_RELRO:
          map->l_relro_addr = h->p_vaddr;
          map->l_relro_size = h->p_memsz;
          break;
        }
    }
  CHECK (map->l_ld != NULL && map->l_tls_blocksize != 0 && map->l_relro_size != 0,
         "loaded dynamic and TLS headers");
  elf_get_dynamic_info (map, false, false);
  _dl_setup_hash (map);
  _dl_assign_tls_modid (map);
}

static void
relocate (struct link_map *map)
{
  const size_t bytes = map->l_info[DT_RELASZ]->d_un.d_val;
  const Elf64_Rela *records = (const void *) D_PTR (map, l_info[DT_RELA]);
  CHECK (bytes != 0 && bytes % sizeof (*records) == 0 && !map->l_relocated,
         "actual GNU ld relocation table");
  const size_t count = bytes / sizeof (*records);
  for (size_t i = 0; i < count; ++i)
    {
      const Elf64_Rela *rela = &records[i];
      CHECK (ELF64_R_TYPE (rela->r_info) == R_X86_64_TPOFF64
             && *(const Elf64_Addr *) (map->l_addr + rela->r_offset) == 0,
             "unrelocated initial-exec GOT slot");
    }

  _dl_relocate_object (map, map->l_scope, 0, 0);

  CHECK (map->l_relocated, "GNU completed the object's relocation");
  for (size_t i = 0; i < count; ++i)
    {
      const uintptr_t target = map->l_addr + records[i].r_offset;
      const uintptr_t page = xos_image_page_start (target);
      CHECK (*(const Elf64_Sxword *) target < 0
             && xos_image_vm (XOS_VM_COMMIT, 0, page, XOS_VM_PAGE, 0, 1) == 0
             && xos_image_vm (XOS_VM_COMMIT, 0, page, XOS_VM_PAGE, 0, 3) != 0,
             "relocated GOT slot is sealed read-only");
    }
}

void d1_run_closure_tls (uintptr_t, uintptr_t, int) __attribute__ ((noreturn));

void
d1_run_closure_tls (uintptr_t provider, uintptr_t consumer, int exhausted)
{
  CHECK (!exhausted, "normal linked closure mode");
  __rtld_malloc_init_stubs ();
  __tls_pre_init_tp ();
  add_module (&maps[0], provider, provider_name);
  add_module (&maps[1], consumer, consumer_name);
  maps[0].l_next = &maps[1];
  maps[1].l_prev = &maps[0];
  GL (dl_ns)[LM_ID_BASE]._ns_loaded = &maps[0];
  GL (dl_ns)[LM_ID_BASE]._ns_nloaded = 2;
  maps[0].l_initfini = startup_maps;
  maps[0].l_searchlist = scope;
  CHECK (maps[0].l_tls_modid == 1 && maps[1].l_tls_modid == 2,
         "distinct GNU TLS modules");

  struct pthread *pd = __xos_rtld_init_tls (0);
  CHECK (pd != NULL && THREAD_SELF == pd, "native initial thread");
  __xos_rtld_init_tls_templates (&maps[0], pd);
  dtv_t *dtv = THREAD_DTV ();
  CHECK (dtv == GL (dl_initial_dtv) && dtv[0].counter == 1, "initial DTV generation");
  relocate (&maps[0]);
  relocate (&maps[1]);
  CHECK (__xos_rtld_heap_seal () == 0, "seal the early heap");

  uint64_t (*provider_call) (uint64_t) = (void *) maps[0].l_entry;
  uint64_t (*consumer_call) (uint64_t) = (void *) maps[1].l_entry;
  CHECK (provider_call (3) == 0x51 && consumer_call (7) == 0x51 + 0xa7,
         "provider errno and real DT_NEEDED TLS access");
  const long now = file_trap (46, 0, 0, 0);
  CHECK (now >= 0 && file_trap (47, now + 40000000, 0, 0) == 0,
         "native dispatch");
  CHECK (THREAD_SELF == pd && THREAD_DTV () == dtv
         && provider_call (0) == 0x51 + 7 + 3 + 256 * 3
         && consumer_call (0) == 0x51 + 0xa7 + 14,
         "relocated errno and both TLS modules survived dispatch");
  static const char success[] = "D1_GNU_RELOC_OK dsos=2 tpoff64=gnu "
                               "relro=sealed errno=dynamic tp=preserved\n";
  stop (success, sizeof (success) - 1, 0);
}
