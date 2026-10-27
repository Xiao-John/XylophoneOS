// SPDX-License-Identifier: Apache-2.0
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main() {
    const char* name = "/中文/程序.txt";
    int fd = open(name, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0 || write(fd, "runtime", 7) != 7 || close(fd) != 0) return 1;
    DIR* dir = opendir("/中文");
    if (!dir) return 2;
    bool seen = false;
    while (struct dirent* entry = readdir(dir)) {
        if (!strcmp(entry->d_name, "程序.txt")) seen = true;
    }
    if (closedir(dir) != 0 || !seen) return 3;
    if (rename(name, "/中文/更名.txt") != 0) return 4;
    fd = open("/中文/更名.txt", O_RDONLY);
    char value[8]{};
    if (fd < 0 || read(fd, value, 7) != 7 || memcmp(value, "runtime", 7) || close(fd)) return 5;
    if (open("/中文/\xff.txt", O_CREAT | O_WRONLY, 0644) >= 0) return 6;
    if (unlink("/中文/更名.txt") != 0) return 7;
    puts("UTF8_LIBC_OK");
    return 0;
}
