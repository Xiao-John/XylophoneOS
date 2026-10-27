/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int run(const char *name, unsigned long count) {
    FILE *f = !strcmp(name, "-") ? stdin : fopen(name, "rb");
    if (!f) { fprintf(stderr, "head: %s: %s\n", name, strerror(errno)); return 1; }
    int c, failed = 0;
    while (count && (c = fgetc(f)) != EOF) { if (putchar(c) == EOF) { failed = 1; break; } if (c == '\n') --count; }
    if (ferror(f)) failed = 1;
    if (f != stdin && fclose(f)) failed = 1;
    return failed;
}
int main(int argc, char **argv) {
    unsigned long count = 10; int first = 1, failed = 0;
    while (first < argc) {
        if (!strcmp(argv[first], "--")) { ++first; break; }
        if (argv[first][0] != '-' || !argv[first][1]) break;
        if (!strcmp(argv[first], "-n") && first + 1 < argc) {
            const char *v = argv[first+1]; char *end; errno = 0;
            if (*v < '0' || *v > '9') { fprintf(stderr, "head: invalid count\n"); return 2; }
            count = strtoul(v, &end, 10); if (*end || errno) { fprintf(stderr, "head: invalid count\n"); return 2; }
            first += 2; continue;
        }
        fprintf(stderr, "head: unsupported option: %s\n", argv[first]); return 2;
    }
    if (first == argc) failed = run("-", count);
    for (int i = first; i < argc; ++i) {
        if (argc-first > 1) printf("%s==> %s <==\n", i > first ? "\n" : "", !strcmp(argv[i], "-") ? "standard input" : argv[i]);
        failed |= run(argv[i], count);
    }
    if (fflush(stdout) == EOF) failed = 1; return failed ? 1 : 0;
}
