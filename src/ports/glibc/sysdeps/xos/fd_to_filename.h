/* SPDX-License-Identifier: Apache-2.0
   XOS has no qualified descriptor-to-path operation.  */
#ifndef XOS_GLIBC_FD_TO_FILENAME_H
#define XOS_GLIBC_FD_TO_FILENAME_H 1
struct fd_to_filename { unsigned char unused; };
__attribute__ ((visibility ("hidden")))
char *__fd_to_filename (int descriptor, struct fd_to_filename *storage);
#endif
