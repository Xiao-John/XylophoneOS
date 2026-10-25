/* SPDX-License-Identifier: MIT */
/* XOS adaptation of sbase cat.c; see ../upstream/LICENSE. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int copy_fd(int input, const char *name) {
    char buffer[4096];
    ssize_t count;
    while ((count = read(input, buffer, sizeof(buffer))) > 0) {
        ssize_t done = 0;
        while (done < count) {
            const ssize_t wrote = write(1, buffer + done, (size_t)(count - done));
            if (wrote <= 0) { perror("cat: write"); return 1; }
            done += wrote;
        }
    }
    if (count < 0) { fprintf(stderr, "cat: %s: %s\n", name, strerror(errno)); return 1; }
    return 0;
}

int main(int argc, char **argv) {
    int result = 0;
    if (argc == 1) { return copy_fd(0, "stdin"); }
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "-u")) { continue; }
        int input = !strcmp(argv[i], "-") ? 0 : open(argv[i], O_RDONLY);
        if (input < 0) { fprintf(stderr, "cat: %s: %s\n", argv[i], strerror(errno)); result = 1; continue; }
        if (copy_fd(input, argv[i]) != 0) { result = 1; }
        if (input != 0) { close(input); }
    }
    return result;
}
