/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_terminal_runtime.h"
#include "xos_file_result.h"
int __tcgetattr (int fd, struct termios *value)
{ return (int) xos_file_result (__xos_terminal_tcgetattr (fd, value)); }
libc_hidden_def (__tcgetattr)
weak_alias (__tcgetattr, tcgetattr)
