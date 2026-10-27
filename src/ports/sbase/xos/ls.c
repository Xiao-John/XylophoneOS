/* SPDX-License-Identifier: Apache-2.0 */
/* Bounded, single-column XOS ls subset. */
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define MAX_ENTRIES 4096u
#define MAX_BYTES (1024u * 1024u)
static int compare(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}
static int list_dir(const char *path, int all, int almost) {
    DIR *dir = opendir(path);
    if (!dir) { fprintf(stderr, "ls: %s: %s\n", path, strerror(errno)); return 1; }
    char **names = calloc(MAX_ENTRIES, sizeof(*names));
    if (!names) { fprintf(stderr, "ls: out of memory\n"); closedir(dir); return 1; }
    size_t count = 0, bytes = 0;
    int failed = 0;
    if (all) {
        names[count++] = strdup("."); names[count++] = strdup("..");
        if (!names[0] || !names[1]) failed = 1;
        bytes = 5;
    }
    while (!failed) {
        errno = 0;
        struct dirent *entry = readdir(dir);
        if (!entry) { if (errno) { fprintf(stderr, "ls: %s: %s\n", path, strerror(errno)); failed = 1; } break; }
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        if (entry->d_name[0] == '.' && !(all || almost)) continue;
        size_t length = strlen(entry->d_name) + 1;
        if (count == MAX_ENTRIES || length > MAX_BYTES - bytes) {
            fprintf(stderr, "ls: %s: directory exceeds list limit\n", path); failed = 1; break;
        }
        names[count] = malloc(length);
        if (!names[count]) { fprintf(stderr, "ls: out of memory\n"); failed = 1; break; }
        memcpy(names[count++], entry->d_name, length); bytes += length;
    }
    if (closedir(dir) != 0) { fprintf(stderr, "ls: %s: %s\n", path, strerror(errno)); failed = 1; }
    if (!failed) {
        qsort(names, count, sizeof(*names), compare);
        for (size_t i = 0; i < count; ++i) {
            if (puts(names[i]) == EOF) { fprintf(stderr, "ls: output error\n"); failed = 1; break; }
        }
    }
    for (size_t i = 0; i < count; ++i) free(names[i]);
    free(names);
    return failed;
}
int main(int argc, char **argv) {
    int all = 0, almost = 0, directory = 0, first = 1, failed = 0;
    for (; first < argc; ++first) {
        const char *arg = argv[first];
        if (!strcmp(arg, "--")) { ++first; break; }
        if (arg[0] != '-' || !arg[1]) break;
        for (const char *p = arg + 1; *p; ++p) {
            if (*p == '1') continue;
            if (*p == 'a') { all = 1; almost = 0; }
            else if (*p == 'A') { almost = 1; all = 0; }
            else if (*p == 'd') directory = 1;
            else { fprintf(stderr, "ls: unsupported option -%c\n", *p); return 2; }
        }
    }
    int count = argc - first;
    if (!count) { argv[--first] = "."; count = 1; }
    int printed = 0;
    for (int i = first; i < argc; ++i) {
        struct stat st;
        if (stat(argv[i], &st)) { fprintf(stderr, "ls: %s: %s\n", argv[i], strerror(errno)); failed = 1; continue; }
        if (directory || !S_ISDIR(st.st_mode)) {
            if (puts(argv[i]) == EOF) failed = 1;
            printed = 1;
        }
    }
    if (!directory) for (int i = first; i < argc; ++i) {
        struct stat st;
        if (stat(argv[i], &st) || !S_ISDIR(st.st_mode)) continue;
        if (printed) putchar('\n');
        if (count > 1) printf("%s:\n", argv[i]);
        failed |= list_dir(argv[i], all, almost); printed = 1;
    }
    if (fflush(stdout) == EOF) failed = 1;
    return failed ? 1 : 0;
}
