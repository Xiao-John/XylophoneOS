/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
int __dup (int fd)
{ return (int) xos_file_result (__xos_file_dup (fd, 0, 0, 0)); }
libc_hidden_def (__dup)
weak_alias (__dup, dup)
