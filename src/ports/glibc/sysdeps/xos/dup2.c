/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
int __dup2 (int fd, int target)
{ return (int) xos_file_result (__xos_file_dup (fd, target, 1, 0)); }
libc_hidden_def (__dup2)
weak_alias (__dup2, dup2)
