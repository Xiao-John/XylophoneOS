/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    int n = argc > 1 && !strcmp(argv[1], "--") ? 2 : 1;
    if (argc - n != 1 || (n == 1 && argv[n][0] == '-' && argv[n][1])) {
        fprintf(stderr, "usage: dirname [--] path\n"); return 2;
    }
    char *p = strdup(argv[n]); if (!p) return 1;
    size_t len = strlen(p);
    while (len > 1 && p[len - 1] == '/') p[--len] = 0;
    char *slash = strrchr(p, '/');
    const char *result = ".";
    if (slash) { while (slash > p && slash[-1] == '/') --slash; if (slash == p) p[1] = 0; else *slash = 0; result = p; }
    int status = puts(result) == EOF || fflush(stdout) == EOF; free(p); return status;
}
