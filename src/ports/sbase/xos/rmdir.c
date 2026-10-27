/* SPDX-License-Identifier: Apache-2.0 */
/* XOS empty-directory-only rmdir subset. */
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    int first = 1, result = 0;
    if (first < argc && !strcmp(argv[first], "--")) ++first;
    if (first == argc) { fprintf(stderr, "usage: rmdir [--] dir ...\n"); return 2; }
    for (int i = first; i < argc; ++i) {
        if (argv[i][0] == '-' && first == 1) { fprintf(stderr, "rmdir: unsupported option: %s\n", argv[i]); return 2; }
        if (rmdir(argv[i])) { fprintf(stderr, "rmdir: %s: %s\n", argv[i], strerror(errno)); result = 1; }
    }
    return result;
}
