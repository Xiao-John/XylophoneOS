/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"
int __fsync (int fd)
{ return (int) xos_file_result (__xos_file_sync (fd)); }
libc_hidden_def (__fsync)
weak_alias (__fsync, fsync)
