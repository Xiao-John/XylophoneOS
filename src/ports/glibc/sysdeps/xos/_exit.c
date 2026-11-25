/* SPDX-License-Identifier: Apache-2.0
   XOS process termination for the experimental glibc port.  */

#include <unistd.h>
#include <stdlib.h>

#if !defined __x86_64__
# error "XOS glibc _exit is implemented only for x86-64"
#endif

void
_exit (int status)
{
  /* XOS sys_exit (2) terminates the whole process.  If it unexpectedly
     returns, trap rather than continue executing after _exit.  */
  __asm__ volatile ("int $0x80" : : "a" (2L), "D" ((long int) status)
                    : "memory", "cc");
  for (;;)
    __asm__ volatile ("ud2");
}
libc_hidden_def (_exit)
rtld_hidden_def (_exit)
weak_alias (_exit, _Exit)
