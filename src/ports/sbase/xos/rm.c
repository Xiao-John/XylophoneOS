/* SPDX-License-Identifier: MIT */
/* XOS non-recursive subset adapted from sbase rm.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    int force = 0, first = 1, result = 0;
    if (argc > 1 && !strcmp(argv[1], "-f")) { force = 1; first = 2; }
    if (first == argc) { return force ? 0 : 2; }
    for (int i = first; i < argc; ++i) {
        struct stat status;
        int removed = stat(argv[i], &status) == 0 && S_ISDIR(status.st_mode)
            ? rmdir(argv[i]) : unlink(argv[i]);
        if (removed < 0 && !(force && errno == ENOENT)) {
            fprintf(stderr, "rm: %s: %s\n", argv[i], strerror(errno)); result = 1;
        }
    }
    return result;
}
