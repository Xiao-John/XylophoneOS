/* SPDX-License-Identifier: Apache-2.0 */
/* Build with the GNU interpreter's actual headers and compile flags. */
#include <ldsodefs.h>
#include <dl-hash.h>
#include <dl-new-hash.h>
#include <errno.h>
#include <pthreadP.h>
#include <string.h>
#include <tls.h>
#include <unistd.h>
#include "get-dynamic-info.h"
#include "xos_file_trap.h"
#include "xos_rtld_heap.h"
#include "xos_rtld_initial_tls.h"
#include "xos_rtld_libc_handoff.h"

static struct link_map map, consumer;
static struct link_map *maps[] = { &consumer, &map };
static struct r_scope_elem scope = { .r_list = maps, .r_nlist = 2 };
static char component_name[] = "libg3.so";
static char consumer_name[] = "g3-user.so";

static _Noreturn void
stop (const char *message, size_t size, int code)
{
  (void) file_trap (1, (uintptr_t) message, size, 0);
  (void) file_trap (2, code, 0, 0);
  __builtin_trap ();
}

#define CHECK(condition, reason)                                       \
  do                                                                   \
    {                                                                  \
      if (!(condition))                                                \
        {                                                              \
          static const char m[] = "D1_LIBC_HANDOFF_FAIL " reason "\n"; \
          stop (m, sizeof (m) - 1, 64);                                 \
        }                                                              \
    }                                                                  \
  while (0)

static void *
lookup (struct link_map *image, const char *name, const char *version)
{
  const Elf64_Sym *symbol = _dl_lookup_direct (image, name, _dl_new_hash (name),
                                               version, _dl_elf_hash (version));
  return symbol == NULL ? NULL : DL_SYMBOL_ADDRESS (image, symbol);
}

static void
add_image (struct link_map *image, uintptr_t bias, char *name)
{
  const Elf64_Ehdr *elf = (const void *) bias;
  image->l_addr = image->l_map_start = bias;
  image->l_entry = bias + elf->e_entry;
  image->l_name = name;
  image->l_real = image;
  image->l_type = lt_library;
  image->l_global = 1;
  image->l_phdr = (const void *) (bias + elf->e_phoff);
  image->l_phnum = elf->e_phnum;
  image->l_scope = image->l_scope_mem;
  image->l_scope_max = sizeof (image->l_scope_mem) / sizeof (*image->l_scope_mem);
  image->l_scope[0] = image->l_local_scope[0] = &scope;
  image->l_searchlist = scope;
  image->l_initfini = maps;
  for (size_t i = 0; i < image->l_phnum; ++i)
    {
      const Elf64_Phdr *ph = &image->l_phdr[i];
      if (ph->p_type == PT_LOAD && bias + ph->p_vaddr + ph->p_memsz > image->l_map_end)
        image->l_map_end = bias + ph->p_vaddr + ph->p_memsz;
      if (ph->p_type == PT_DYNAMIC)
        {
          image->l_ld = (void *) (bias + ph->p_vaddr);
          image->l_ld_readonly = !(ph->p_flags & PF_W);
        }
      if (ph->p_type == PT_TLS)
        {
          CHECK (ph->p_memsz != 0 && ph->p_align != 0, "shared libc TLS");
          image->l_tls_align = ph->p_align;
          image->l_tls_blocksize = ph->p_memsz;
          image->l_tls_firstbyte_offset = ph->p_vaddr & (ph->p_align - 1);
          image->l_tls_initimage = (void *) (bias + ph->p_vaddr);
          image->l_tls_initimage_size = ph->p_filesz;
        }
      if (ph->p_type == PT_GNU_RELRO)
        {
          image->l_relro_addr = ph->p_vaddr;
          image->l_relro_size = ph->p_memsz;
        }
    }
  CHECK (image->l_ld != NULL && image->l_relro_size != 0, "real shared data headers");
  elf_get_dynamic_info (image, false, false);
  _dl_setup_hash (image);
}

static void
relocate (uintptr_t bias, uintptr_t consumer_bias)
{
  add_image (&consumer, consumer_bias, consumer_name);
  add_image (&map, bias, component_name);
  CHECK (map.l_tls_blocksize != 0 && consumer.l_tls_blocksize == 0
         && consumer.l_info[DT_JMPREL] != NULL && consumer.l_info[DT_PLTRELSZ] != NULL
         && consumer.l_info[DT_PLTRELSZ]->d_un.d_val == 3 * sizeof (Elf64_Rela),
         "shared TLS and three external PLT relocations");
  consumer.l_next = &map;
  map.l_prev = &consumer;
  _dl_assign_tls_modid (&map);
  GL (dl_ns)[LM_ID_BASE]._ns_loaded = &consumer;
  GL (dl_ns)[LM_ID_BASE]._ns_nloaded = 2;
  struct pthread *pd = __xos_rtld_init_tls (0);
  CHECK (pd != NULL && THREAD_SELF == pd, "native initial rtld TLS");
  __xos_rtld_init_tls_templates (&consumer, pd);
  CHECK (_dl_check_map_versions (&map, 0, 0) == 0
         && _dl_check_map_versions (&consumer, 0, 0) == 0, "GNU symbol versions");
  _dl_relocate_object (&map, map.l_scope, 0, 0);
  _dl_relocate_object (&consumer, consumer.l_scope, 0, 0);
  CHECK (consumer.l_relocated && map.l_relocated && map.l_versyms != NULL && map.l_versions != NULL,
         "GNU relocation and version table");
  const Elf64_Rela *plt = (const void *) D_PTR (&consumer, l_info[DT_JMPREL]);
  for (size_t i = 0; i < 3; ++i)
    {
      const uintptr_t slot = consumer_bias + plt[i].r_offset;
      const uintptr_t target = *(const Elf64_Addr *) slot;
      CHECK (ELF64_R_TYPE (plt[i].r_info) == R_X86_64_JUMP_SLOT
             && target >= map.l_map_start && target < map.l_map_end
             && xos_image_vm (XOS_VM_COMMIT, 0, xos_image_page_start (slot), XOS_VM_PAGE, 0, 3) != 0,
             "external symbol bound into the provider and RELRO sealed");
    }
}

void d1_run_libc_handoff (uintptr_t, uintptr_t, struct xos_rtld_images *, xos_u32, xos_u32, int)
  __attribute__ ((noreturn));

void
d1_run_libc_handoff (uintptr_t bias, uintptr_t consumer_bias, struct xos_rtld_images *images,
                     xos_u32 version, xos_u32 inherited, int wrong_version)
{
  __rtld_malloc_init_stubs ();
  __tls_pre_init_tp ();
  relocate (bias, consumer_bias);
  int (*consume) (int, const char *, size_t) = (void *) consumer.l_entry;
  long (*sequence) (void) = lookup (&map, "d1_handoff_sequence", "GLIBC_PRIVATE");
  CHECK (sequence != NULL, "native request observer");

  const int fd = version == 3 ? 10 : 0;
  const xos_u32 before = images->files->request_sequence;
  CHECK (consume (fd, "EFGH", 4) == -EIO,
         "shared fd table is unavailable before handoff");
  CHECK (images->files->request_sequence == before, "no early file exchange");
  if (wrong_version)
    {
      CHECK (__xos_rtld_handoff_libc_files (&map, images) == ENOEXEC
             && images->files->phase == xos_file_session_active
             && images->files->request_sequence == before + 2
             && consume (fd, "EFGH", 4) == -EIO,
             "wrong symbol version closes pins without transferring");
      images->request = (struct xos_file_request) { .operation = 5, .handle = inherited, .length = 4 };
      CHECK (__xos_file_session_call (images->files, &images->request, &images->response) == 0
             && images->response.length == 4 && memcmp (images->response.data, "EFGH", 4) == 0,
             "refused candidate leaves the active early owner");
      images->request = (struct xos_file_request) { .operation = 8, .handle = inherited };
      CHECK (__xos_file_session_call (images->files, &images->request, &images->response) == 0,
             "release inherited input after refusal");
      static const char refused[] = "D1_LIBC_HANDOFF_REFUSED version=checked files=early\n";
      stop (refused, sizeof (refused) - 1, 0);
    }

  xos_file_startup_receiver adopt = lookup (&map, "__xos_file_adopt_startup", "GLIBC_PRIVATE");
  const long now = file_trap (46, 0, 0, 0);
  CHECK (adopt != NULL && now > 0 && adopt (images->files, now) == -ETIMEDOUT
         && images->files->phase == xos_file_session_active && images->files->request_sequence == before,
         "expired transfer preserves early ownership");
  CHECK (__xos_rtld_handoff_libc_files (&map, images) == 0
         && images->files->request_sequence == before + 2
         && images->files->phase == xos_file_session_transferred,
         "released pin and single real session transfer");
  CHECK (adopt (images->files, __xos_rtld_heap_deadline ()) == -EBUSY
         && __xos_file_session_call (images->files, &images->request, &images->response) == -EIO,
         "no second owner or repeated transfer");
  CHECK (__xos_rtld_heap_seal () == 0, "seal native early heap");
  if (version == 3)
    {
      CHECK (consume (12, "E", 1) == -EBADF
             && consume (10, "EF", 2) == 0 && consume (11, "GH", 2) == 0
             && sequence () == (long) before + 7,
             "exec alias position, CLOEXEC close, shared errno and sequence");
      static const char success[] = "D1_LIBC_HANDOFF_OK native=v3 inherited=EFGH alias=shared cloexec=closed sequence=continuous consumer=dt_needed\n";
      stop (success, sizeof (success) - 1, 0);
    }
  CHECK (consume (0, "EFGH", 4) == 0 && sequence () == (long) before + 5,
         "spawn descriptor and shared request sequence");
  static const char success[] = "D1_LIBC_HANDOFF_OK native=v2 inherited=EFGH sequence=continuous consumer=dt_needed\n";
  stop (success, sizeof (success) - 1, 0);
}
