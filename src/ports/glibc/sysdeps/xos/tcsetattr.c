/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_terminal_runtime.h"
#include "xos_file_result.h"
int __tcsetattr (int fd, int action, const struct termios *value)
{ return (int) xos_file_result (__xos_terminal_tcsetattr (fd, action, value)); }
libc_hidden_def (__tcsetattr)
weak_alias (__tcsetattr, tcsetattr)
