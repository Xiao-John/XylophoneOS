/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
off64_t __libc_lseek64 (int fd, off64_t offset, int origin)
{ return xos_file_result (__xos_file_seek (fd, offset, origin)); }
strong_alias (__libc_lseek64, __lseek64)
libc_hidden_def (__lseek64)
weak_alias (__libc_lseek64, lseek64)
