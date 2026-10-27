/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define LIMIT (1024u*1024u)
static int run(const char *name, unsigned long count) {
    FILE *f = !strcmp(name, "-") ? stdin : fopen(name, "rb");
    if (!f) { fprintf(stderr, "tail: %s: %s\n", name, strerror(errno)); return 1; }
    unsigned char *buffer = malloc(LIMIT); if (!buffer) { if (f != stdin) fclose(f); return 1; }
    size_t start = 0, used = 0; unsigned long lines = 0; int c, failed = 0;
    while ((c = fgetc(f)) != EOF) {
        if (!count) continue;
        if (used == LIMIT) { fprintf(stderr, "tail: retained text exceeds 1 MiB\n"); failed = 1; break; }
        buffer[(start + used++) % LIMIT] = (unsigned char)c;
        if (c == '\n') ++lines;
        while (lines > count) {
            unsigned char b = buffer[start]; start = (start + 1) % LIMIT; --used;
            if (b == '\n') --lines;
        }
    }
    if (ferror(f)) failed = 1;
    if (!failed && used && buffer[(start + used - 1) % LIMIT] != '\n' && lines == count) {
        while (used) { unsigned char b = buffer[start]; start = (start + 1) % LIMIT; --used; if (b == '\n') break; }
    }
    if (!failed) for (size_t i = 0; i < used; ++i) if (putchar(buffer[(start+i)%LIMIT]) == EOF) { failed = 1; break; }
    free(buffer); if (f != stdin && fclose(f)) failed = 1; return failed;
}
int main(int argc, char **argv) {
    unsigned long count = 10; int first = 1, failed = 0;
    while (first < argc) {
        if (!strcmp(argv[first], "--")) { ++first; break; }
        if (argv[first][0] != '-' || !argv[first][1]) break;
        if (!strcmp(argv[first], "-n") && first + 1 < argc) {
            const char *v = argv[first+1]; char *end; errno = 0;
            if (*v < '0' || *v > '9') { fprintf(stderr, "tail: invalid count\n"); return 2; }
            count = strtoul(v, &end, 10); if (*end || errno) { fprintf(stderr, "tail: invalid count\n"); return 2; }
            first += 2; continue;
        }
        fprintf(stderr, "tail: unsupported option: %s\n", argv[first]); return 2;
    }
    if (first == argc) failed = run("-", count);
    for (int i = first; i < argc; ++i) {
        if (argc-first > 1) printf("%s==> %s <==\n", i > first ? "\n" : "", !strcmp(argv[i], "-") ? "standard input" : argv[i]);
        failed |= run(argv[i], count);
    }
    if (fflush(stdout) == EOF) failed = 1; return failed ? 1 : 0;
}
