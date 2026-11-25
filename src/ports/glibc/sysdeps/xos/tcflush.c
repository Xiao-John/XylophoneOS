/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_terminal_runtime.h"
#include "xos_file_result.h"
int __tcflush (int fd, int queue)
{ return (int) xos_file_result (__xos_terminal_tcflush (fd, queue)); }
libc_hidden_def (__tcflush)
weak_alias (__tcflush, tcflush)
