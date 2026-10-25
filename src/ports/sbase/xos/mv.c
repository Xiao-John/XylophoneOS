/* SPDX-License-Identifier: MIT */
/* XOS same-volume subset adapted from sbase mv.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    int first = argc > 1 && !strcmp(argv[1], "-f") ? 2 : 1;
    if (argc - first != 2) { fprintf(stderr, "usage: mv [-f] source dest\n"); return 2; }
    if (rename(argv[first], argv[first + 1]) < 0) {
        fprintf(stderr, "mv: %s -> %s: %s\n", argv[first], argv[first + 1], strerror(errno));
        return 1;
    }
    return 0;
}
