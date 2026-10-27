/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    int n = argc > 1 && !strcmp(argv[1], "--") ? 2 : 1;
    if (argc - n < 1 || argc - n > 2 || (n == 1 && argv[n][0] == '-' && argv[n][1])) {
        fprintf(stderr, "usage: basename [--] path [suffix]\n"); return 2;
    }
    char *p = strdup(argv[n]); if (!p) return 1;
    size_t len = strlen(p);
    if (!len) { free(p); return puts(".") == EOF; }
    while (len > 1 && p[len - 1] == '/') p[--len] = 0;
    char *name = strrchr(p, '/'); name = name ? name + 1 : p;
    if (!*name) name = p;
    size_t size = strlen(name);
    if (argc - n == 2) { size_t suffix = strlen(argv[n+1]);
        if (suffix < size && suffix && !strcmp(name + size - suffix, argv[n+1])) name[size - suffix] = 0;
    }
    int status = puts(name) == EOF || fflush(stdout) == EOF; free(p); return status;
}
