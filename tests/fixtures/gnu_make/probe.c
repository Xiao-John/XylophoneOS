/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static int append_marker(const char *path)
{
    FILE *file = fopen(path, "a");
    if (file == NULL)
        return 1;
    int result = fputs("ran\n", file);
    int closed = fclose(file);
    return result < 0 || closed != 0;
}

static int wait_for_peer(const char *mine, const char *peer)
{
    struct timespec start, now;
    if (append_marker(mine) || clock_gettime(CLOCK_MONOTONIC, &start))
        return 1;
    while (access(peer, F_OK) != 0) {
        if (errno != ENOENT || clock_gettime(CLOCK_MONOTONIC, &now)
            || now.tv_sec - start.tv_sec >= 8)
            return 2;
        sched_yield();
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 4 && !strcmp(argv[1], "peer"))
        return wait_for_peer(argv[2], argv[3]);
    if (argc == 3 && !strcmp(argv[1], "append"))
        return append_marker(argv[2]);
    if (argc == 3 && !strcmp(argv[1], "fail"))
        return append_marker(argv[2]) ? 1 : 7;
    if (argc == 3 && !strcmp(argv[1], "absent"))
        return !(access(argv[2], F_OK) == -1 && errno == ENOENT);
    if (argc == 2 && !strcmp(argv[1], "emit")) {
        puts("real-pipe-data");
        return fflush(stdout) == EOF;
    }
    if (argc == 2 && !strcmp(argv[1], "verify")) {
        char buffer[32];
        if (fgets(buffer, sizeof(buffer), stdin) == NULL
            || strcmp(buffer, "real-pipe-data\n") || getchar() != EOF || ferror(stdin))
            return 3;
        puts("GNU_MAKE_PIPE_OK");
        return 0;
    }
    return 4;
}
