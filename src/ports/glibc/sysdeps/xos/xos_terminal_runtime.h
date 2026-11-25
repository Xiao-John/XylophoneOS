/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_TERMINAL_RUNTIME_H
#define XOS_GLIBC_TERMINAL_RUNTIME_H 1
#include "xos_file_wire.h"
#include <stddef.h>
#include <termios.h>

/* Private C bridge. The C++ adapter checks the canonical native ABI and
   copies each field; no libc struct is ever used as a protocol message. */
struct xos_terminal_mode
{
  xos_u32 iflag, oflag, cflag, lflag, ispeed, ospeed, vmin, vtime;
};
#ifdef __cplusplus
extern "C" {
#endif
long __xos_terminal_restore (const struct xos_file_startup *)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_close (void) __attribute__ ((visibility ("hidden")));
long __xos_terminal_read (void *, size_t, unsigned int)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_write (const void *, size_t, unsigned int)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_get_mode (struct xos_terminal_mode *)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_set_mode (const struct xos_terminal_mode *, unsigned int)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_drain (void) __attribute__ ((visibility ("hidden")));
long __xos_terminal_flush_input (void) __attribute__ ((visibility ("hidden")));

long __xos_terminal_tcgetattr (int, struct termios *)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_tcsetattr (int, int, const struct termios *)
  __attribute__ ((visibility ("hidden")));
long __xos_terminal_tcdrain (int) __attribute__ ((visibility ("hidden")));
long __xos_terminal_tcflush (int, int) __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
