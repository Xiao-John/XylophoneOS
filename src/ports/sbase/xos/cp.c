/* SPDX-License-Identifier: MIT AND Apache-2.0 */
/* Upstream-derived MIT portions retained; XOS changes from 2026-10-27 are Apache-2.0. */
/* XOS regular-file subset adapted from sbase cp.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    int first = 1;
    if (argc > 1 && !strcmp(argv[1], "--")) first = 2;
    else if (argc > 1 && argv[1][0] == '-' && argv[1][1]) { fprintf(stderr, "cp: unsupported option: %s\n", argv[1]); return 2; }
    if (argc - first != 2) { fprintf(stderr, "usage: cp [--] source dest\n"); return 2; }
    const char *source = argv[first], *target = argv[first + 1];
    char destination[256];
    struct stat source_status, target_status;
    if (stat(source, &source_status) < 0) { fprintf(stderr, "cp: %s: %s\n", source, strerror(errno)); return 1; }
    if (!S_ISREG(source_status.st_mode)) { fprintf(stderr, "cp: %s: not a regular file\n", source); return 1; }
    if (stat(target, &target_status) == 0 && S_ISDIR(target_status.st_mode)) {
        const char *base = strrchr(source, '/'); base = base ? base + 1 : source;
        if (!*base || snprintf(destination, sizeof(destination), "%s/%s", target, base) >= (int)sizeof(destination)) {
            fprintf(stderr, "cp: invalid or overlong target\n"); return 1;
        }
        target = destination;
    }
    if (stat(target, &target_status) == 0) {
        if (source_status.st_dev == target_status.st_dev && source_status.st_ino == target_status.st_ino) {
            fprintf(stderr, "cp: %s and %s are the same file\n", source, target); return 1;
        }
    } else if (errno != ENOENT) { fprintf(stderr, "cp: %s: %s\n", target, strerror(errno)); return 1; }
    int input = open(source, O_RDONLY);
    if (input < 0) { fprintf(stderr, "cp: %s: %s\n", source, strerror(errno)); return 1; }
    int output = open(target, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (output < 0) { fprintf(stderr, "cp: %s: %s\n", target, strerror(errno)); close(input); return 1; }
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
    if (close(input) < 0) { result = 1; }
    return result;
}
