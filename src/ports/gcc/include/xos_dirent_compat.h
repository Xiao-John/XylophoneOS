// SPDX-License-Identifier: Apache-2.0
#pragma once
/* XOS dirent exposes only regular files and directories.  libstdc++'s
   filesystem switch still names the POSIX d_type constants; keep the named
   constants available without pretending special files exist. */
#include <dirent.h>
#ifndef DT_FIFO
#define DT_FIFO 1
#endif
#ifndef DT_CHR
#define DT_CHR 2
#endif
#ifndef DT_BLK
#define DT_BLK 6
#endif
#ifndef DT_LNK
#define DT_LNK 10
#endif
#ifndef DT_SOCK
#define DT_SOCK 12
#endif
