/* SPDX-License-Identifier: Apache-2.0
   Compile with the candidate glibc SDK, not a host or legacy libc sysroot. */
#define _GNU_SOURCE 1
#include <stddef.h>
#include <fcntl.h>
#include <sys/stat.h>
_Static_assert (sizeof (struct stat) == 120, "XOS glibc stat size");
_Static_assert (sizeof (struct stat64) == sizeof (struct stat), "LP64 stat64");
_Static_assert (offsetof (struct stat, st_atim) == 48, "stat timespec offset");
_Static_assert (offsetof (struct stat, st_rdev) == 96, "stat device offset");
_Static_assert (O_APPEND == 8 && O_CREAT == 0x200 && O_TRUNC == 0x400, "open flags");
_Static_assert (O_NONBLOCK == 0x4000 && O_CLOEXEC == 0x40000, "startup flags");
_Static_assert (O_DIRECTORY == 0x200000 && O_NOFOLLOW == 0x100000, "path flags");
_Static_assert (F_DUPFD_CLOEXEC == 14 && FD_CLOEXEC == 1, "descriptor flags");
_Static_assert (AT_EMPTY_PATH == 0x1000, "empty path dispatch");
