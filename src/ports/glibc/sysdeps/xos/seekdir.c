/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
void __seekdir (DIR *directory, long position)
{ (void) xos_file_result (__xos_directory_seek (directory, position)); }
weak_alias (__seekdir, seekdir)
