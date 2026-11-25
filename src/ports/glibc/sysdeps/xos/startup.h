/* SPDX-License-Identifier: Apache-2.0
   Early failures must work before TLS, errno and stdio are initialized.  */
#ifndef XOS_GLIBC_STARTUP_H
#define XOS_GLIBC_STARTUP_H 1
static inline __attribute__ ((noreturn)) void
xos_startup_fatal (const char *message)
{
  unsigned long length = 0;
  while (message[length] != 0)
    ++length;
  long ignored;
  __asm__ volatile ("int $0x80" : "=a" (ignored) : "a" (1UL), "D" (message),
                    "S" (length), "d" (0UL) : "memory", "cc");
  __asm__ volatile ("int $0x80" : "=a" (ignored) : "a" (2UL), "D" (127UL),
                    "S" (0UL), "d" (0UL) : "memory", "cc");
  __builtin_trap ();
}
#define _startup_fatal(message) xos_startup_fatal (message)
#endif
