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

static struct link_map map;
static struct link_map *maps[] = { &map };
static struct r_scope_elem scope = { .r_list = maps, .r_nlist = 1 };
static char component_name[] = "libg3.so";

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
relocate (uintptr_t bias)
{
  const Elf64_Ehdr *elf = (const void *) bias;
  map.l_addr = map.l_map_start = bias;
  map.l_name = component_name;
  map.l_real = &map;
  map.l_type = lt_library;
  map.l_global = 1;
  map.l_phdr = (const void *) (bias + elf->e_phoff);
  map.l_phnum = elf->e_phnum;
  map.l_scope = map.l_scope_mem;
  map.l_scope_max = sizeof (map.l_scope_mem) / sizeof (*map.l_scope_mem);
  map.l_scope[0] = map.l_local_scope[0] = &scope;
  map.l_searchlist = scope;
  map.l_initfini = maps;
  for (size_t i = 0; i < map.l_phnum; ++i)
    {
      const Elf64_Phdr *ph = &map.l_phdr[i];
      if (ph->p_type == PT_LOAD && bias + ph->p_vaddr + ph->p_memsz > map.l_map_end)
        map.l_map_end = bias + ph->p_vaddr + ph->p_memsz;
      if (ph->p_type == PT_DYNAMIC)
        {
          map.l_ld = (void *) (bias + ph->p_vaddr);
          map.l_ld_readonly = !(ph->p_flags & PF_W);
        }
      if (ph->p_type == PT_TLS)
        {
          CHECK (ph->p_memsz != 0 && ph->p_align != 0, "shared libc TLS");
          map.l_tls_align = ph->p_align;
          map.l_tls_blocksize = ph->p_memsz;
          map.l_tls_firstbyte_offset = ph->p_vaddr & (ph->p_align - 1);
          map.l_tls_initimage = (void *) (bias + ph->p_vaddr);
          map.l_tls_initimage_size = ph->p_filesz;
        }
      if (ph->p_type == PT_GNU_RELRO)
        {
          map.l_relro_addr = ph->p_vaddr;
          map.l_relro_size = ph->p_memsz;
        }
    }
  CHECK (map.l_ld != NULL && map.l_tls_blocksize != 0 && map.l_relro_size != 0,
         "real shared data headers");
  elf_get_dynamic_info (&map, false, false);
  _dl_setup_hash (&map);
  _dl_assign_tls_modid (&map);
  GL (dl_ns)[LM_ID_BASE]._ns_loaded = &map;
  GL (dl_ns)[LM_ID_BASE]._ns_nloaded = 1;
  struct pthread *pd = __xos_rtld_init_tls (0);
  CHECK (pd != NULL && THREAD_SELF == pd, "native initial rtld TLS");
  __xos_rtld_init_tls_templates (&map, pd);
  CHECK (_dl_check_map_versions (&map, 0, 0) == 0, "GNU symbol versions");
  _dl_relocate_object (&map, map.l_scope, 0, 0);
  CHECK (map.l_relocated && map.l_versyms != NULL && map.l_versions != NULL,
         "GNU relocation and version table");
}

void d1_run_libc_handoff (uintptr_t, struct xos_rtld_images *, xos_u32, xos_u32, int)
  __attribute__ ((noreturn));

void
d1_run_libc_handoff (uintptr_t bias, struct xos_rtld_images *images,
                     xos_u32 version, xos_u32 inherited, int wrong_version)
{
  __rtld_malloc_init_stubs ();
  __tls_pre_init_tp ();
  relocate (bias);
  ssize_t (*read_fd) (int, void *, size_t) = lookup (&map, "read", "GLIBC_2.44");
  int (*close_fd) (int) = lookup (&map, "close", "GLIBC_2.44");
  int *(*errno_address) (void) = lookup (&map, "__errno_location", "GLIBC_PRIVATE");
  long (*sequence) (void) = lookup (&map, "d1_handoff_sequence", "GLIBC_PRIVATE");
  CHECK (read_fd != NULL && close_fd != NULL && errno_address != NULL && sequence != NULL,
         "real versioned shared libc file exports");

  char bytes[4];
  const int fd = version == 3 ? 10 : 0;
  const xos_u32 before = images->files->request_sequence;
  CHECK (read_fd (fd, bytes, sizeof (bytes)) == -1 && *errno_address () == EIO,
         "shared fd table is unavailable before handoff");
  CHECK (images->files->request_sequence == before, "no early file exchange");
  if (wrong_version)
    {
      CHECK (__xos_rtld_handoff_libc_files (&map, images) == ENOEXEC
             && images->files->phase == xos_file_session_active
             && images->files->request_sequence == before + 1
             && read_fd (fd, bytes, sizeof (bytes)) == -1 && *errno_address () == EIO,
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
         && images->files->request_sequence == before + 1
         && images->files->phase == xos_file_session_transferred,
         "released pin and single real session transfer");
  CHECK (adopt (images->files, __xos_rtld_heap_deadline ()) == -EBUSY
         && __xos_file_session_call (images->files, &images->request, &images->response) == -EIO,
         "no second owner or repeated transfer");
  CHECK (__xos_rtld_heap_seal () == 0, "seal native early heap");
  if (version == 3)
    {
      CHECK (read_fd (12, bytes, 1) == -1 && *errno_address () == EBADF
             && read_fd (10, bytes, 2) == 2 && memcmp (bytes, "EF", 2) == 0 && close_fd (10) == 0
             && read_fd (11, bytes, 2) == 2 && memcmp (bytes, "GH", 2) == 0 && close_fd (11) == 0
             && sequence () == (long) before + 6,
             "exec alias position, CLOEXEC close, shared errno and sequence");
      static const char success[] = "D1_LIBC_HANDOFF_OK native=v3 inherited=EFGH alias=shared cloexec=closed sequence=continuous\n";
      stop (success, sizeof (success) - 1, 0);
    }
  CHECK (read_fd (0, bytes, 4) == 4 && memcmp (bytes, "EFGH", 4) == 0 && close_fd (0) == 0
         && sequence () == (long) before + 4, "spawn descriptor and shared request sequence");
  static const char success[] = "D1_LIBC_HANDOFF_OK native=v2 inherited=EFGH sequence=continuous\n";
  stop (success, sizeof (success) - 1, 0);
}
