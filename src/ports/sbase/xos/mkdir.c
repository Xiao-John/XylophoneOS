/* SPDX-License-Identifier: MIT AND Apache-2.0 */
/* Upstream-derived MIT portions retained; XOS changes from 2026-10-27 are Apache-2.0. */
/* XOS no-mode-bits subset adapted from sbase mkdir.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

static int make_parents(const char *path) {
    char copy[256];
    size_t length = strlen(path);
    if (length == 0 || length >= sizeof(copy)) { errno = ENAMETOOLONG; return -1; }
    memcpy(copy, path, length + 1);
    for (char *at = copy + (copy[0] == '/'); *at; ++at) {
        if (*at != '/') { continue; }
        *at = '\0';
        if (mkdir(copy, 0777) < 0) {
            struct stat st;
            if (errno != EEXIST || stat(copy, &st) < 0 || !S_ISDIR(st.st_mode)) { return -1; }
        }
        *at = '/';
    }
    if (mkdir(copy, 0777) == 0) return 0;
    struct stat st;
    return errno == EEXIST && stat(copy, &st) == 0 && S_ISDIR(st.st_mode) ? 0 : -1;
}

int main(int argc, char **argv) {
    int parents = 0, first = 1, result = 0;
    while (first < argc) {
        if (!strcmp(argv[first], "--")) { ++first; break; }
        if (argv[first][0] != '-' || !argv[first][1]) break;
        if (!strcmp(argv[first], "-p")) { parents = 1; ++first; continue; }
        fprintf(stderr, "mkdir: unsupported option: %s\n", argv[first]); return 2;
    }
    if (first == argc) { fprintf(stderr, "usage: mkdir [-p] dir ...\n"); return 2; }
    for (int i = first; i < argc; ++i) {
        int status = parents ? make_parents(argv[i]) : mkdir(argv[i], 0777);
        if (status < 0) { fprintf(stderr, "mkdir: %s: %s\n", argv[i], strerror(errno)); result = 1; }
    }
    return result;
}
