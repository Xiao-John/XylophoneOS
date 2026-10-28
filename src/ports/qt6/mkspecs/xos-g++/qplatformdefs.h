// SPDX-License-Identifier: Apache-2.0
// Experimental: Qt's POSIX declarations are subject to actual XOS SDK support.
#include <unistd.h>
#include <pthread.h>
#include <dirent.h>
#include <fcntl.h>
#include <sys/time.h>
#define QT_NO_SOCKET_H
#define QT_NO_NATIVE_POLL
#include "../common/posix/qplatformdefs.h"

// XOS off_t is 64-bit; no separate large-file open flag exists.
#undef QT_OPEN_LARGEFILE
#define QT_OPEN_LARGEFILE 0

// XOS file service currently exposes no symbolic links.
#undef QT_LSTAT
#define QT_LSTAT ::stat
