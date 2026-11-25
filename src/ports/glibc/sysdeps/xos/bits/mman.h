/* SPDX-License-Identifier: Apache-2.0 */
#ifndef _SYS_MMAN_H
# error "Never use <bits/mman.h> directly; include <sys/mman.h> instead."
#endif

#define PROT_NONE 0
#define PROT_READ 1
#define PROT_WRITE 2
#define PROT_EXEC 4
#define MAP_SHARED 0x01
#define MAP_PRIVATE 0x02
#define MAP_FIXED 0x10
#define MAP_ANONYMOUS 0x20
#define MAP_ANON MAP_ANONYMOUS
#define MAP_FIXED_NOREPLACE 0x100000

#ifdef __USE_MISC
# define MADV_NORMAL 0
# define MADV_RANDOM 1
# define MADV_SEQUENTIAL 2
# define MADV_WILLNEED 3
# define MADV_DONTNEED 4
#endif

#ifdef __USE_XOPEN2K
# define POSIX_MADV_NORMAL 0
# define POSIX_MADV_RANDOM 1
# define POSIX_MADV_SEQUENTIAL 2
# define POSIX_MADV_WILLNEED 3
# define POSIX_MADV_DONTNEED 4
#endif

#define MS_ASYNC 1
#define MS_SYNC 0
#define MS_INVALIDATE 2
#define MCL_CURRENT 1
#define MCL_FUTURE 2
