// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct __xos_DIR DIR;
struct dirent {
    ino_t d_ino;
    unsigned char d_type;
    char d_name[256];
};

#define DT_UNKNOWN 0
#define DT_DIR 4
#define DT_REG 8

DIR* opendir(const char* path);
struct dirent* readdir(DIR* directory);
int closedir(DIR* directory);
void rewinddir(DIR* directory);

#ifdef __cplusplus
}
#endif
