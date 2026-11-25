/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/auxv.h>
#include <sys/param.h>
#include <sys/stat.h>
#include <unistd.h>

static __thread uint64_t initialized_tls = UINT64_C (0x123456789abcdeff);
static __thread uint64_t zero_tls;
static int constructor_ran;
static int exit_phase;

static void __attribute__ ((constructor))
before_main (void)
{
  constructor_ran = initialized_tls == UINT64_C (0x123456789abcdeff)
                    && zero_tls == 0 && errno == 0;
  initialized_tls ^= 0x5a;
}

static void
second_exit (void)
{
  if (exit_phase != 0)
    _exit (120);
  exit_phase = 1;
  puts ("G2 atexit second");
}

static void
first_exit (void)
{
  if (exit_phase != 1)
    _exit (121);
  exit_phase = 2;
  puts ("G2 atexit first");
}

static void __attribute__ ((destructor))
after_main (void)
{
  if (exit_phase != 2)
    _exit (122);
  puts ("G2 destructor ok");
}

#define CHECK(condition) do { if (!(condition)) { \
  fprintf (stderr, "G2 failure line=%d errno=%d\n", __LINE__, errno); \
  _exit (90); } } while (0)

int
main (int argc, char **argv, char **envp)
{
  CHECK ((argc == 2 || argc == 3) && strcmp (argv[1], "alpha") == 0 && argv[argc] == NULL);
  CHECK (argc != 3 || strcmp (argv[2], "exit") == 0);
  CHECK (envp != NULL && getenv ("PATH") != NULL
         && strcmp (getenv ("PATH"), "/usr/bin:/bin:/") == 0);
  CHECK (setvbuf (stdout, NULL, _IOFBF, 1024) == 0);
  CHECK (constructor_ran && initialized_tls == (UINT64_C (0x123456789abcdeff) ^ 0x5a));
  CHECK (getauxval (AT_PAGESZ) == 4096 && getauxval (AT_PHNUM) == 4);
  CHECK (getpid () > 0);
  CHECK (EXEC_PAGESIZE == 4096);
  zero_tls = 0xfedcba9876543210UL;
  errno = EDOM;
  CHECK (zero_tls == 0xfedcba9876543210UL && getpagesize () == 4096 && errno == EDOM);
  CHECK (write (99, "x", 1) == -1 && errno == EBADF);
  CHECK (read (1, NULL, 0) == -1 && errno == EBADF);
  CHECK (read (0, NULL, 0) == 0 && write (2, NULL, 0) == 0);
  errno = 0;
  CHECK (strtol ("99999999999999999999999999", NULL, 10) == LONG_MAX && errno == ERANGE);

  const size_t sizes[] = { 1, 31, 4097, 131077, 1048593 };
  for (size_t i = 0; i < sizeof (sizes) / sizeof (sizes[0]); ++i)
    {
      unsigned char *p = malloc (sizes[i]);
      CHECK (p != NULL && (uintptr_t) p % 16 == 0);
      memset (p, 0x5c, sizes[i]);
      p = realloc (p, sizes[i] + 37);
      CHECK (p != NULL && p[0] == 0x5c && p[sizes[i] - 1] == 0x5c);
      free (p);
    }
  uint64_t *zeros = calloc (257, sizeof (*zeros));
  CHECK (zeros != NULL);
  for (size_t i = 0; i < 257; ++i)
    CHECK (zeros[i] == 0);
  free (zeros);
  void *aligned = aligned_alloc (4096, 8192);
  CHECK (aligned != NULL && (uintptr_t) aligned % 4096 == 0);
  free (aligned);
  volatile size_t impossible = SIZE_MAX;
  void *(*volatile observed_malloc) (size_t) = malloc;
  errno = 0;
  CHECK (observed_malloc (impossible) == NULL && errno == ENOMEM);

  jmp_buf checkpoint;
  int jumped = setjmp (checkpoint);
  if (jumped == 0)
    longjmp (checkpoint, 7);
  CHECK (jumped == 7);

  char formatted[80];
  CHECK (snprintf (formatted, sizeof (formatted), "%s:%d:%" PRIx64,
                   "glibc", 42, zero_tls) == 25);
  CHECK (strcmp (formatted, "glibc:42:fedcba9876543210") == 0);
  char wide[512];
  memset (wide, '.', sizeof (wide));
  memcpy (wide, "G2 wide write ", 14);
  wide[sizeof (wide) - 1] = '\n';
  CHECK (fwrite (wide, 1, sizeof (wide), stdout) == sizeof (wide)
         && fflush (stdout) == 0);
  CHECK (atexit (first_exit) == 0 && atexit (second_exit) == 0);
  printf ("G2 main ok: %s\n", formatted);
  /* The final newline stays in the stdio buffer until normal exit. */
  CHECK (fputs ("G2 buffered exit\n", stdout) >= 0);
  if (argc == 3)
    exit (39);
  return 37;
}
