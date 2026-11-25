/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
int __close (int fd)
{ return (int) xos_file_result (__xos_file_close (fd)); }
libc_hidden_def (__close)
weak_alias (__close, close)
