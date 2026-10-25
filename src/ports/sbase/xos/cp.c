/* SPDX-License-Identifier: MIT */
/* XOS regular-file subset adapted from sbase cp.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: cp source dest\n"); return 2; }
    struct stat source_status, target_status;
    if (stat(argv[1], &source_status) < 0 || !S_ISREG(source_status.st_mode)) {
        fprintf(stderr, "cp: %s: %s\n", argv[1], strerror(errno)); return 1;
    }
    if (stat(argv[2], &target_status) == 0 && source_status.st_dev == target_status.st_dev &&
        source_status.st_ino == target_status.st_ino) {
        fprintf(stderr, "cp: %s and %s are the same file\n", argv[1], argv[2]); return 1;
    }
    int input = open(argv[1], O_RDONLY);
    if (input < 0) { fprintf(stderr, "cp: %s: %s\n", argv[1], strerror(errno)); return 1; }
    int output = open(argv[2], O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (output < 0) { fprintf(stderr, "cp: %s: %s\n", argv[2], strerror(errno)); close(input); return 1; }
    char buffer[4096];
    int result = 0;
    for (;;) {
        const ssize_t count = read(input, buffer, sizeof(buffer));
        if (count == 0) { break; }
        if (count < 0) { fprintf(stderr, "cp: read: %s\n", strerror(errno)); result = 1; break; }
        ssize_t done = 0;
        while (done < count) {
            const ssize_t wrote = write(output, buffer + done, (size_t)(count - done));
            if (wrote <= 0) { fprintf(stderr, "cp: write: %s\n", strerror(errno)); result = 1; break; }
            done += wrote;
        }
        if (result) { break; }
    }
    if (close(output) < 0) { result = 1; }
    close(input);
    return result;
}
