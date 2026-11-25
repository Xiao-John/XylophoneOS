/* SPDX-License-Identifier: Apache-2.0
   Public XOS glibc flags. Values used in startup v2/v3 match the existing SDK.
   This installed header is self-contained: sysdeps include_next fallbacks
   exist only while building glibc and cannot be used by SDK consumers. */
#ifndef _FCNTL_H
# error "Include <fcntl.h> before this implementation header."
#endif
#ifndef _XOS_BITS_FCNTL_H
#define _XOS_BITS_FCNTL_H 1
#include <bits/types.h>

#define O_RDONLY 0
#define O_WRONLY 1
#define O_RDWR 2
#define O_ACCMODE 3
#define O_APPEND 0x0008
#define O_ASYNC 0x0040
#define O_CREAT 0x0200
#define O_TRUNC 0x0400
#define O_EXCL 0x0800
#define O_FSYNC 0x2000
#define O_SYNC O_FSYNC
#define O_NONBLOCK 0x4000
#define O_NOCTTY 0x8000
#define __O_CLOEXEC 0x40000

#ifdef __USE_MISC
# define O_NDELAY O_NONBLOCK
# define O_SHLOCK 0x0010
# define O_EXLOCK 0x0020
# define FREAD 1
# define FWRITE 2
# define FASYNC O_ASYNC
# define FFSYNC O_FSYNC
# define FSYNC O_SYNC
# define FAPPEND O_APPEND
# define FNDELAY O_NDELAY
#endif
#ifdef __USE_XOPEN2K8
# define O_CLOEXEC __O_CLOEXEC
# define O_NOFOLLOW 0x100000
# define O_DIRECTORY 0x200000
# define F_DUPFD_CLOEXEC 14
#endif
#if defined __USE_POSIX199309 || defined __USE_UNIX98
# define O_DSYNC O_SYNC
# define O_RSYNC O_SYNC
#endif
#ifdef __USE_LARGEFILE64
# define O_LARGEFILE 0
#endif

#define F_DUPFD 0
#define F_GETFD 1
#define F_SETFD 2
#define F_GETFL 3
#define F_SETFL 4
#if defined __USE_UNIX98 || defined __USE_XOPEN2K8
# define F_GETOWN 5
# define F_SETOWN 6
#endif
#define F_GETLK 7
#define F_SETLK 8
#define F_SETLKW 9
#define F_GETLK64 F_GETLK
#define F_SETLK64 F_SETLK
#define F_SETLKW64 F_SETLKW
#define FD_CLOEXEC 1
#define F_RDLCK 1
#define F_WRLCK 2
#define F_UNLCK 3

/* Advisory locks currently fail with ENOTSUP. Their public layout remains
   available for compilation, with the same 64-bit offsets in both types. */
struct flock
{
  __off_t l_start, l_len;
  __pid_t l_pid;
  short l_type, l_whence;
};
#ifdef __USE_LARGEFILE64
struct flock64
{
  __off64_t l_start, l_len;
  __pid_t l_pid;
  short l_type, l_whence;
};
#endif

#ifdef __USE_XOPEN2K
# define POSIX_FADV_NORMAL 0
# define POSIX_FADV_RANDOM 1
# define POSIX_FADV_SEQUENTIAL 2
# define POSIX_FADV_WILLNEED 3
# define POSIX_FADV_DONTNEED 4
# define POSIX_FADV_NOREUSE 5
#endif
#endif
