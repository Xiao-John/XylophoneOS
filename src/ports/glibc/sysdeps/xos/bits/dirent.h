/* SPDX-License-Identifier: Apache-2.0
   XOS LP64 dirent: retain the generic field prefix, bound names at 255 bytes. */
#ifndef _DIRENT_H
# error "Include <dirent.h> instead of <bits/dirent.h>."
#endif
struct dirent
{
  __ino_t d_ino;
  unsigned short d_reclen;
  unsigned char d_type;
  unsigned char d_namlen;
  char d_name[256];
};
#ifdef __USE_LARGEFILE64
struct dirent64
{
  __ino64_t d_ino;
  unsigned short d_reclen;
  unsigned char d_type;
  unsigned char d_namlen;
  char d_name[256];
};
#endif
#define d_fileno d_ino
#define _DIRENT_HAVE_D_RECLEN 1
#define _DIRENT_HAVE_D_NAMLEN 1
#define _DIRENT_HAVE_D_TYPE 1
#define _DIRENT_MATCHES_DIRENT64 1
