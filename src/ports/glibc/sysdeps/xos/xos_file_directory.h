/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_DIRECTORY_H
#define XOS_GLIBC_FILE_DIRECTORY_H 1
#include <dirent.h>
#ifdef __cplusplus
extern "C" {
#endif
long __xos_directory_open (int, DIR **) __attribute__ ((visibility ("hidden")));
long __xos_directory_close (DIR *) __attribute__ ((visibility ("hidden")));
long __xos_directory_read (DIR *, struct dirent **)
  __attribute__ ((visibility ("hidden")));
long __xos_directory_read_copy (DIR *, struct dirent *, struct dirent **)
  __attribute__ ((visibility ("hidden")));
long __xos_directory_seek (DIR *, long) __attribute__ ((visibility ("hidden")));
long __xos_directory_tell (DIR *) __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
