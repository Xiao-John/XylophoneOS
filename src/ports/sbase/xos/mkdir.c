/* SPDX-License-Identifier: MIT */
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
        if (mkdir(copy, 0777) < 0 && errno != EEXIST) { return -1; }
        *at = '/';
    }
    return mkdir(copy, 0777) == 0 || errno == EEXIST ? 0 : -1;
}

int main(int argc, char **argv) {
    int parents = 0, first = 1, result = 0;
    if (argc > 1 && !strcmp(argv[1], "-p")) { parents = 1; first = 2; }
    if (first == argc) { fprintf(stderr, "usage: mkdir [-p] dir ...\n"); return 2; }
    for (int i = first; i < argc; ++i) {
        int status = parents ? make_parents(argv[i]) : mkdir(argv[i], 0777);
        if (status < 0) { fprintf(stderr, "mkdir: %s: %s\n", argv[i], strerror(errno)); result = 1; }
    }
    return result;
}
