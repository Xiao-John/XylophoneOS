/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
struct counts { unsigned long long lines, words, bytes; };
static int space(unsigned char c) { return c == ' ' || (c >= '\t' && c <= '\r'); }
static int run(const char *name, struct counts *out) {
    FILE *f = !strcmp(name, "-") ? stdin : fopen(name, "rb");
    if (!f) { fprintf(stderr, "wc: %s: %s\n", name, strerror(errno)); return 1; }
    int c, in_word = 0, failed = 0;
    while ((c = fgetc(f)) != EOF) {
        if (out->bytes == UINT64_MAX) { failed = 1; break; }
        ++out->bytes; if (c == '\n') ++out->lines;
        if (space((unsigned char)c)) in_word = 0;
        else if (!in_word) { ++out->words; in_word = 1; }
    }
    if (ferror(f)) failed = 1;
    if (f != stdin && fclose(f)) failed = 1;
    if (failed) fprintf(stderr, "wc: %s: read error or overflow\n", name);
    return failed;
}
static void show(struct counts c, int l, int w, int b, const char *label) {
    if (l) printf("%llu", c.lines);
    if (w) printf("%s%llu", l ? " " : "", c.words);
    if (b) printf("%s%llu", l || w ? " " : "", c.bytes);
    if (label) printf(" %s", label);
    putchar('\n');
}
int main(int argc, char **argv) {
    int first = 1, l = 0, w = 0, b = 0, failed = 0; struct counts total = {0,0,0};
    while (first < argc) {
        if (!strcmp(argv[first], "--")) { ++first; break; }
        if (argv[first][0] != '-' || !argv[first][1]) break;
        for (const char *p = argv[first]+1; *p; ++p) {
            if (*p == 'l') l=1; else if (*p == 'w') w=1; else if (*p == 'c') b=1;
            else { fprintf(stderr, "wc: unsupported option -%c\n", *p); return 2; }
        }
        ++first;
    }
    if (!(l || w || b)) l = w = b = 1;
    if (first == argc) { struct counts c = {0,0,0}; failed = run("-", &c); if (!failed) show(c,l,w,b,0); }
    for (int i = first; i < argc; ++i) {
        struct counts c = {0,0,0}; if (run(argv[i], &c)) { failed = 1; continue; }
        if (UINT64_MAX - total.lines < c.lines || UINT64_MAX - total.words < c.words || UINT64_MAX - total.bytes < c.bytes) { failed = 1; continue; }
        total.lines += c.lines; total.words += c.words; total.bytes += c.bytes; show(c,l,w,b,argv[i]);
    }
    if (argc-first > 1) show(total,l,w,b,"total");
    if (fflush(stdout) == EOF) failed = 1; return failed ? 1 : 0;
}
