/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include "xos_file_session.h"
#include "xos_file_trap.h"

/* This wrapper precedes the genuine static XOS glibc entry and TLS setup.
   It exercises the private bridge without standing in for the interpreter. */
extern void __real___xos_glibc_start (const struct xos_file_startup *, void *)
  __attribute__ ((noreturn));
xos_u32 d1_file_early_sequence;
long d1_file_early_failure;

static struct xos_file_session early;
static struct xos_file_request request;
static struct xos_file_response response;

static void __attribute__ ((noreturn))
fail (unsigned int code)
{
  static const char text[] = "D1_FILE_EARLY_FAIL\n";
  (void) file_trap (1, (xos_u64) text, sizeof (text) - 1, 0);
  (void) file_trap (2, (xos_u64) code, 0, 0);
  __builtin_trap ();
}

static int
first_bytes (unsigned int operation, xos_u32 handle)
{
  request.operation = (xos_file_u16) operation;
  request.handle = handle;
  request.length = 4;
  if (__xos_file_session_call (&early, &request, &response) != 0
      || response.length != 4 || response.request_id != early.request_sequence)
    return 0;
  return response.data[0] == 'A' && response.data[1] == 'B'
    && response.data[2] == 'C' && response.data[3] == 'D';
}

static long
open_path (const char *path, unsigned int size)
{
  request.operation = file_open;
  request.handle = 0;
  request.length = 0;
  request.flags = 1; /* Native read_only. */
  request.name_length = size - 1;
  for (unsigned int i = 0; i < size; ++i) request.name[i] = path[i];
  return __xos_file_session_call (&early, &request, &response);
}

void __attribute__ ((noreturn))
__wrap___xos_glibc_start (const struct xos_file_startup *startup, void *stack_top)
{
  const xos_u64 startup_base = 0x7fffc000ULL, startup_end = 0x80000000ULL;
  if ((xos_u64) startup != startup_base || startup->magic != 0x3154524154535358ULL
      || startup->version != 2 || startup->size != sizeof (*startup) || startup->reserved != 64
      || startup->argc < 1 || startup->argc > 2 || (startup->argv & 7) != 0
      || startup->argv < startup_base
      || startup->argv > startup_end - (startup->argc + 1) * sizeof (xos_u64))
    fail (30);
  const struct xos_file_startup_extension *extension =
    (const void *) ((const char *) startup + 64);
  if (extension->magic != 0x32585445534f5855ULL || (extension->flags & 0x100U) == 0
      || extension->file_handles[0] == 0 || extension->open_paths[0] != 0)
    fail (31);
  if (!first_bytes (5, extension->file_handles[0])  /* Sequential read. */
      || !first_bytes (30, extension->file_handles[0])) /* Positioned read at zero. */
    fail (32);
  static const char missing[] = "/d1-file-session-absent";
  if (open_path (missing, sizeof (missing)) != -ENOENT || early.phase != xos_file_session_active)
    fail (33);
  if (startup->argc == 2)
    {
      const xos_u64 *arguments = (const xos_u64 *) startup->argv;
      if (arguments[1] < startup_base || arguments[1] > startup_end - 6)
        fail (34);
      const char *mode = (const char *) arguments[1];
      if (mode[0] != 'd' || mode[1] != 'e' || mode[2] != 'a'
          || mode[3] != 't' || mode[4] != 'h' || mode[5] != 0)
        fail (34);
      /* The existing disposable kernel profile exits the real files service. */
      static const char death[] = "/.glibc_g3_service_death";
      d1_file_early_failure = open_path (death, sizeof (death));
      if ((d1_file_early_failure != -EIO && d1_file_early_failure != -ETIMEDOUT)
          || early.phase != xos_file_session_failed)
        fail (35);
    }
  d1_file_early_sequence = early.request_sequence;
  if (__xos_file_adopt_early_session (&early) != 0 || early.phase != xos_file_session_transferred)
    fail (36);
  if (__xos_file_session_call (&early, &request, &response) != -EIO
      || early.request_sequence != d1_file_early_sequence
      || __xos_file_adopt_early_session (&early) != -EBUSY)
    fail (37);
  __real___xos_glibc_start (startup, stack_top);
}
