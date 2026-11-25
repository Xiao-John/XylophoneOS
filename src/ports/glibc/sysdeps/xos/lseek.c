/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
off_t __libc_lseek (int fd, off_t offset, int origin)
{ return xos_file_result (__xos_file_seek (fd, offset, origin)); }
strong_alias (__libc_lseek, __lseek)
libc_hidden_def (__lseek)
weak_alias (__libc_lseek, lseek)
