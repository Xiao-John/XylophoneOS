/* SPDX-License-Identifier: MIT AND Apache-2.0 */
/* Upstream-derived MIT portions retained; XOS changes from 2026-10-27 are Apache-2.0. */
/* XOS non-recursive subset adapted from sbase rm.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv) {
    int force = 0, first = 1, result = 0;
    while (first < argc) {
        if (!strcmp(argv[first], "--")) { ++first; break; }
        if (argv[first][0] != '-' || !argv[first][1]) break;
        if (!strcmp(argv[first], "-f")) { force = 1; ++first; continue; }
        fprintf(stderr, "rm: unsupported option: %s\n", argv[first]); return 2;
    }
    if (first == argc) { return force ? 0 : 2; }
    for (int i = first; i < argc; ++i) {
        struct stat status;
        int removed;
        if (stat(argv[i], &status) == 0 && S_ISDIR(status.st_mode)) { errno = EISDIR; removed = -1; }
        else { removed = unlink(argv[i]); }
        if (removed < 0 && !(force && errno == ENOENT)) {
            fprintf(stderr, "rm: %s: %s\n", argv[i], strerror(errno)); result = 1;
        }
    }
    return result;
}
