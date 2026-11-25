/* SPDX-License-Identifier: Apache-2.0
   XOS glibc x86-64 stat ABI. This is a libc structure, never an IPC record. */
#if !defined _SYS_STAT_H && !defined _FCNTL_H
# error "Include <sys/stat.h> or <fcntl.h> instead of <bits/stat.h>."
#endif
#ifndef _BITS_STAT_H
#define _BITS_STAT_H 1
#include <bits/types.h>
#include <bits/types/struct_timespec.h>

/* XOS is LP64 and uses 64-bit offsets in both public interfaces. */
#define __XOS_STAT_FIELDS \
  __mode_t st_mode; \
  __ino64_t st_ino; \
  __dev_t st_dev; \
  __nlink_t st_nlink; \
  __uid_t st_uid; \
  __gid_t st_gid; \
  __off64_t st_size; \
  struct timespec st_atim; \
  struct timespec st_mtim; \
  struct timespec st_ctim; \
  __dev_t st_rdev; \
  __blksize_t st_blksize; \
  __blkcnt64_t st_blocks
struct stat { __XOS_STAT_FIELDS; };
#ifdef __USE_LARGEFILE64
struct stat64 { __XOS_STAT_FIELDS; };
#endif
#undef __XOS_STAT_FIELDS

#define st_atime st_atim.tv_sec
#define st_mtime st_mtim.tv_sec
#define st_ctime st_ctim.tv_sec
#define _STATBUF_ST_BLKSIZE 1
#define _STATBUF_ST_RDEV 1
#define _STATBUF_ST_NSEC 1
#define __S_IFMT 0170000
#define __S_IFDIR 0040000
#define __S_IFCHR 0020000
#define __S_IFBLK 0060000
#define __S_IFREG 0100000
#define __S_IFIFO 0010000
#define __S_IFLNK 0120000
#define __S_IFSOCK 0140000
#define __S_ISUID 04000
#define __S_ISGID 02000
#define __S_ISVTX 01000
#define __S_IREAD 0400
#define __S_IWRITE 0200
#define __S_IEXEC 0100
#define __S_TYPEISMQ(buffer) 0
#define __S_TYPEISSEM(buffer) 0
#define __S_TYPEISSHM(buffer) 0
#endif
