/* SPDX-License-Identifier: MIT AND Apache-2.0 */
/* Upstream-derived MIT portions retained; XOS changes from 2026-10-27 are Apache-2.0. */
/* XOS same-volume subset adapted from sbase mv.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

int main(int argc, char **argv) {
    int first = 1;
    if (argc > 1 && !strcmp(argv[1], "--")) first = 2;
    else if (argc > 1 && argv[1][0] == '-' && argv[1][1]) { fprintf(stderr, "mv: unsupported option: %s\n", argv[1]); return 2; }
    if (argc - first != 2) { fprintf(stderr, "usage: mv [--] source dest\n"); return 2; }
    const char *source = argv[first], *target = argv[first + 1];
    char destination[256]; struct stat info;
    if (stat(target, &info) == 0 && S_ISDIR(info.st_mode)) {
        const char *base = strrchr(source, '/'); base = base ? base + 1 : source;
        if (!*base || snprintf(destination, sizeof(destination), "%s/%s", target, base) >= (int)sizeof(destination)) {
            fprintf(stderr, "mv: invalid or overlong target\n"); return 1;
        }
        target = destination;
    }
    if (rename(source, target) < 0) {
        fprintf(stderr, "mv: %s -> %s: %s\n", source, target, strerror(errno));
        return 1;
    }
    return 0;
}
