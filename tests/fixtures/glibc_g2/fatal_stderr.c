/* SPDX-License-Identifier: Apache-2.0 */
#include <string.h>
#include <unistd.h>

extern void __libc_fatal (const char *message) __attribute__ ((noreturn));

int
main (void)
{
  static const char prefix[] = "G2 fatal stderr begin:";
  static const char suffix[] = ":G2 fatal stderr end\n";
  char message[sizeof (prefix) - 1 + 300 + sizeof (suffix)];
  memcpy (message, prefix, sizeof (prefix) - 1);
  memset (message + sizeof (prefix) - 1, '.', 300);
  memcpy (message + sizeof (prefix) - 1 + 300, suffix, sizeof (suffix));

  if (close (STDOUT_FILENO) != 0)
    return 90;
  __libc_fatal (message);
}
