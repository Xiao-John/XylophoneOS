/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
int __ftruncate64 (int fd, off64_t length)
{ return (int) xos_file_result (__xos_file_truncate (fd, length)); }
libc_hidden_def (__ftruncate64)
weak_alias (__ftruncate64, ftruncate64)
