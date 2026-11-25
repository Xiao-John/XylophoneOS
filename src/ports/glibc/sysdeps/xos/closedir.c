/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
int __closedir (DIR *directory)
{ return (int) xos_file_result (__xos_directory_close (directory)); }
weak_alias (__closedir, closedir)
