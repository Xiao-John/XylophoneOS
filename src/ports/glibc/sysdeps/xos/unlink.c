/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>
#include "xos_file_result.h"

libc_hidden_proto (__unlink)

int __unlink (const char *path)
{ return (int) xos_file_result (__xos_file_path_op (path, 13)); }
libc_hidden_def (__unlink)
weak_alias (__unlink, unlink)
