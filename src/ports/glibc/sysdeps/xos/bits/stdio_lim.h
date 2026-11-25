/* SPDX-License-Identifier: Apache-2.0
   XOS-specific stdio limits for the experimental glibc port.  */
#ifndef _BITS_STDIO_LIM_H
#define _BITS_STDIO_LIM_H 1
#ifndef _STDIO_H
# error "Never include <bits/stdio_lim.h> directly; use <stdio.h> instead."
#endif
/* The current XOS file-service path buffer is 256 bytes including NUL.  */
#define FILENAME_MAX 256
#endif
