/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_terminal_runtime.h"
#include "xos_file_result.h"
int __tcdrain (int fd)
{ return (int) xos_file_result (__xos_terminal_tcdrain (fd)); }
libc_hidden_def (__tcdrain)
weak_alias (__tcdrain, tcdrain)
