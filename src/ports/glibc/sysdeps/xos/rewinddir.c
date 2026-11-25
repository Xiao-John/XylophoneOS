/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
void __rewinddir (DIR *directory) { (void) xos_file_result (__xos_directory_seek (directory, 0)); }
libc_hidden_def (__rewinddir)
weak_alias (__rewinddir, rewinddir)
