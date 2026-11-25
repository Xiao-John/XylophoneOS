/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
int __ftruncate (int fd, off_t length)
{ return (int) xos_file_result (__xos_file_truncate (fd, length)); }
libc_hidden_def (__ftruncate)
weak_alias (__ftruncate, ftruncate)
