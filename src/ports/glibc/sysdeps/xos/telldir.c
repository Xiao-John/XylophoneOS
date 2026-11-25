/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_file_directory.h"
#include "xos_file_result.h"
long telldir (DIR *directory) { return xos_file_result (__xos_directory_tell (directory)); }
