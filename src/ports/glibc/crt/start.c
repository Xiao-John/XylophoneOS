/* SPDX-License-Identifier: Apache-2.0
   XOS startup v1/v2/v3 entry; this is not a Linux process entry ABI.  */
#include <stdint.h>
#include <stddef.h>
#include <elf.h>

struct xos_startup_info
{
  uint64_t magic;
  uint32_t version, size, argc, handle_count;
  uint64_t argv;
  uint32_t handles[3], reserved;
};
struct xos_startup_extension
{
  uint64_t magic;
  uint32_t environment_count, flags;
  uint64_t environment, working_directory, open_paths[3];
  uint32_t open_flags[3], file_handles[3], reserved;
};
struct xos_startup_exec
{
  uint64_t magic, descriptors;
  uint32_t count, reserved;
};
_Static_assert (sizeof (struct xos_startup_info) == 48, "startup prefix");
_Static_assert (sizeof (struct xos_startup_extension) == 88, "startup extension");

const void *__xos_startup __attribute__ ((visibility ("hidden")));
/* Bit zero is supplied only by the G3 descriptor backend.  In the basic
   console SDK, reject file inheritance before any constructors can run. */
extern const unsigned int __xos_file_startup_capabilities
  __attribute__ ((weak, visibility ("hidden")));
extern int main (int, char **, char **);
extern int __libc_start_main (int (*) (int, char **, char **), int, char **,
                             void *, void *, void *, void *)
  __attribute__ ((noreturn));
extern const Elf64_Ehdr __ehdr_start;

static inline long
native_call (unsigned long number, unsigned long a, unsigned long b)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (a), "S" (b), "d" (0UL)
                    : "memory", "cc");
  return result;
}

static __attribute__ ((noreturn)) void
fail_message (const char *text, size_t length)
{
  native_call (1, (uintptr_t) text, length);
  native_call (2, 127, 0);
  __builtin_trap ();
}

static __attribute__ ((noreturn)) void
fail (void)
{
  static const char text[] = "XOS glibc: invalid startup or entropy unavailable\n";
  fail_message (text, sizeof (text) - 1);
}

static __attribute__ ((noreturn)) void
unsupported (void)
{
  static const char text[] = "XOS glibc: unsupported startup extension\n";
  fail_message (text, sizeof (text) - 1);
}

static int
within (uintptr_t start, size_t length, uintptr_t begin, uintptr_t end)
{
  return start >= begin && start <= end && length <= end - start;
}

static int
string_in_startup (uintptr_t address, uintptr_t begin, uintptr_t end)
{
  if (!within (address, 1, begin, end))
    return 0;
  const char *string = (const char *) address;
  for (size_t i = 0; i < 4096 && i < end - address; ++i)
    if (string[i] == 0)
      return 1;
  return 0;
}

__attribute__ ((noreturn, visibility ("hidden"))) void
__xos_glibc_start (const struct xos_startup_info *startup, void *stack_top)
{
  /* The startup mapping has a fixed, bounded range in the native ABI. */
  const uintptr_t begin = 0x7fffc000UL, end = 0x80000000UL;
  if ((uintptr_t) startup != begin || startup->magic != 0x3154524154535358UL
      || startup->version < 1 || startup->version > 3 || startup->argc > 64
      || startup->handle_count != 3 || startup->size != sizeof (*startup)
      || (startup->argv & 7) != 0
      || !within (startup->argv, (startup->argc + 1UL) * sizeof (char *), begin, end))
    fail ();
  const int file_descriptors = &__xos_file_startup_capabilities != NULL
                              && (__xos_file_startup_capabilities & 1) != 0;
  for (uint32_t i = 0; i < 3; ++i)
    if (startup->handles[i] > 2)
      fail ();
    else if (!file_descriptors && startup->handles[i] != i)
      unsupported ();
  const char *const *original = (const char *const *) startup->argv;
  if (original[startup->argc] != NULL)
    fail ();
  uint32_t environment_count = 0;
  const char *const *environment = NULL;
  if (startup->version >= 2)
    {
      if (startup->reserved != 64)
        fail ();
      const struct xos_startup_extension *extension = (const void *) (begin + 64);
      environment_count = extension->environment_count;
      if (extension->magic != 0x32585445534f5855UL || environment_count > 64
          || (extension->environment & 7) != 0
          || (extension->flags & ~0x10707U) != 0
          || ((extension->flags & 0x10000U) == 0 ? extension->reserved != 0
                                                  : extension->reserved == 0)
          || !within (extension->environment, (environment_count + 1UL) * sizeof (char *), begin, end))
        fail ();
      if (extension->working_directory != 0
          && !string_in_startup (extension->working_directory, begin, end))
        fail ();
      for (uint32_t i = 0; i < 3; ++i)
        {
          if (extension->open_paths[i] != 0
              && !string_in_startup (extension->open_paths[i], begin, end))
            fail ();
          if (((extension->flags >> (8 + i)) & 1)
              != (extension->file_handles[i] != 0))
            fail ();
          if (extension->open_paths[i] != 0)
            unsupported ();
        }
      if ((extension->flags & 0x10000U) != 0
          || (!file_descriptors && (extension->flags & 0x700U) != 0))
        unsupported ();
      if (startup->version == 3)
        {
          const struct xos_startup_exec *execution = (const void *) (begin + 152);
          if (execution->magic != 0x335845534f585546UL || execution->reserved != 0
              || execution->count > 32 || (execution->descriptors & 7) != 0
              || !within (execution->descriptors, execution->count * 24UL, begin, end))
            fail ();
          if (!file_descriptors)
            unsupported ();
        }
      environment = (const char *const *) extension->environment;
      if (environment[environment_count] != NULL)
        fail ();
    }
  else if (startup->reserved != 0)
    fail ();

  /* libc discovers envp and auxv consecutively after argv.  Keep that
     private representation alive on the initial stack until process exit. */
  uintptr_t words[64 + 1 + 64 + 1 + 7 * 2];
  size_t next = 0;
  for (uint32_t i = 0; i < startup->argc; ++i)
    {
      if (!string_in_startup ((uintptr_t) original[i], begin, end))
        fail ();
      words[next++] = (uintptr_t) original[i];
    }
  words[next++] = 0;
  for (uint32_t i = 0; i < environment_count; ++i)
    {
      if (!string_in_startup ((uintptr_t) environment[i], begin, end))
        fail ();
      words[next++] = (uintptr_t) environment[i];
    }
  words[next++] = 0;
  unsigned char random[16];
  if (native_call (63, (uintptr_t) random, sizeof (random)) != 0)
    fail ();
  words[next++] = AT_PHDR;
  words[next++] = (uintptr_t) &__ehdr_start + __ehdr_start.e_phoff;
  words[next++] = AT_PHNUM; words[next++] = __ehdr_start.e_phnum;
  words[next++] = AT_PHENT; words[next++] = sizeof (Elf64_Phdr);
  words[next++] = AT_PAGESZ; words[next++] = 4096;
  words[next++] = AT_RANDOM; words[next++] = (uintptr_t) random;
  words[next++] = AT_SECURE; words[next++] = 0;
  words[next++] = AT_NULL; words[next++] = 0;
  __xos_startup = startup;
  __libc_start_main (main, startup->argc, (char **) words, NULL, NULL, NULL,
                     stack_top);
}
