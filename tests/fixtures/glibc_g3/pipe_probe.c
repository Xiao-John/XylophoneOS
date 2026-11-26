/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#define CHECK(expression) do {                                             \
    if (!(expression)) {                                                   \
        fprintf(stderr, "GLIBC_PIPE_FAILURE line=%d errno=%d\n", __LINE__, errno); \
        return 1;                                                          \
    }                                                                      \
} while (0)

static int nonblocking(void)
{
    int ends[2] = { 41, 43 };
    CHECK(pipe2(ends, O_CREAT) == -1 && errno == EINVAL);
    CHECK(ends[0] == 41 && ends[1] == 43);
    CHECK(pipe2(ends, O_CLOEXEC | O_NONBLOCK) == 0);
    CHECK(ends[0] == 3 && ends[1] == 4);
    CHECK(fcntl(ends[0], F_GETFD) == FD_CLOEXEC && fcntl(ends[1], F_GETFD) == FD_CLOEXEC);
    CHECK(fcntl(ends[0], F_GETFL) == (O_NONBLOCK | O_RDONLY));
    CHECK(fcntl(ends[1], F_GETFL) == (O_NONBLOCK | O_WRONLY));
    struct stat info;
    CHECK(fstat(ends[0], &info) == 0 && S_ISFIFO(info.st_mode));
    unsigned char bytes[PIPE_BUF];
    CHECK(read(ends[1], bytes, 1) == -1 && errno == EBADF);
    CHECK(write(ends[0], "x", 1) == -1 && errno == EBADF);
    CHECK(read(ends[0], bytes, 1) == -1 && errno == EAGAIN);
    int alias = dup(ends[1]);
    CHECK(alias == 5 && fcntl(alias, F_GETFD) == 0);
    CHECK(fcntl(alias, F_SETFL, O_WRONLY) == 0);
    CHECK(fcntl(ends[1], F_GETFL) == O_WRONLY);
    CHECK(fcntl(ends[1], F_SETFL, O_WRONLY | O_NONBLOCK) == 0);
    CHECK(fcntl(alias, F_GETFL) == (O_WRONLY | O_NONBLOCK));
    CHECK(close(ends[1]) == 0);
    CHECK(read(ends[0], bytes, 1) == -1 && errno == EAGAIN);
    memset(bytes, 0xe4, sizeof(bytes));
    CHECK(write(alias, bytes, sizeof(bytes)) == sizeof(bytes));
    CHECK(read(ends[0], bytes, 5) == 5);
    CHECK(write(alias, "atomic", 6) == -1 && errno == EAGAIN);
    unsigned char large[PIPE_BUF + 1];
    memset(large, 0x53, sizeof(large));
    CHECK(write(alias, large, sizeof(large)) == 5);
    CHECK(close(alias) == 0);
    CHECK(read(ends[0], bytes, sizeof(bytes)) == sizeof(bytes));
    for (size_t i = 0; i < sizeof(bytes); ++i)
        CHECK(bytes[i] == (i < sizeof(bytes) - 5 ? 0xe4 : 0x53));
    CHECK(read(ends[0], bytes, 1) == 0);
    CHECK(close(ends[0]) == 0);

    CHECK(pipe(ends) == 0);
    CHECK(close(ends[0]) == 0);
    CHECK(write(ends[1], "x", 1) == -1 && errno == EPIPE);
    CHECK(close(ends[1]) == 0);
    puts("GLIBC_PIPE_NONBLOCK_PASS");
    return 0;
}

static int capacity(void)
{
    int aliases[28];
    for (size_t i = 0; i < sizeof(aliases) / sizeof(aliases[0]); ++i) {
        aliases[i] = fcntl(STDOUT_FILENO, F_DUPFD_CLOEXEC, 3);
        CHECK(aliases[i] >= 0);
    }
    int ends[2] = { 41, 43 };
    CHECK(pipe(ends) == -1 && errno == EMFILE && ends[0] == 41 && ends[1] == 43);
    CHECK(close_range(aliases[1], aliases[0], 0) == -1 && errno == EINVAL);
    CHECK(close_range(aliases[0], aliases[1], 1) == -1 && errno == EINVAL);
    CHECK(fcntl(aliases[0], F_GETFD) == FD_CLOEXEC);
    const size_t last = sizeof(aliases) / sizeof(aliases[0]) - 1;
    CHECK(close_range(aliases[0], aliases[last] - 1, 0) == 0);
    for (size_t i = 0; i < last; ++i)
        CHECK(fcntl(aliases[i], F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(aliases[last], F_GETFD) == FD_CLOEXEC);
    closefrom(aliases[last]);
    CHECK(fcntl(aliases[last], F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(STDOUT_FILENO, F_GETFD) == 0);
    CHECK(close_range(UINT_MAX, UINT_MAX, 0) == 0);

    int pairs[8][2];
    for (size_t i = 0; i < sizeof(pairs) / sizeof(pairs[0]); ++i)
        CHECK(pipe(pairs[i]) == 0);
    CHECK(pipe(ends) == -1 && errno == ENFILE && ends[0] == 41 && ends[1] == 43);
    for (size_t i = 0; i < sizeof(pairs) / sizeof(pairs[0]); ++i)
        CHECK(close(pairs[i][0]) == 0 && close(pairs[i][1]) == 0);
    CHECK(pipe(ends) == 0 && ends[0] == 3 && ends[1] == 4);
    CHECK(close(ends[0]) == 0 && close(ends[1]) == 0);
    puts("GLIBC_PIPE_CAPACITY_PASS");
    return 0;
}

static unsigned char payload[2 * PIPE_BUF + 1845];

struct writer {
    int fd;
    ssize_t count;
    int closed;
};

static void *produce(void *argument)
{
    struct writer *writer = argument;
    writer->count = write(writer->fd, payload, sizeof(payload));
    writer->closed = close(writer->fd);
    return NULL;
}

static int thread_stdio(void)
{
    int ends[2];
    CHECK(pipe(ends) == 0);
    CHECK(fcntl(ends[0], F_GETFD) == 0 && fcntl(ends[1], F_GETFD) == 0);
    CHECK(fcntl(ends[0], F_GETFL) == O_RDONLY && fcntl(ends[1], F_GETFL) == O_WRONLY);
    for (size_t i = 0; i < sizeof(payload); ++i)
        payload[i] = (unsigned char) (i % 251);
    struct writer writer = { ends[1], -1, -1 };
    pthread_t thread;
    CHECK(pthread_create(&thread, NULL, produce, &writer) == 0);
    size_t total = 0;
    for (;;) {
        unsigned char bytes[997];
        ssize_t count = read(ends[0], bytes, sizeof(bytes));
        CHECK(count >= 0);
        if (count == 0) break;
        CHECK(total + (size_t) count <= sizeof(payload));
        CHECK(memcmp(bytes, payload + total, (size_t) count) == 0);
        total += (size_t) count;
    }
    CHECK(pthread_join(thread, NULL) == 0);
    CHECK(total == sizeof(payload) && writer.count == sizeof(payload) && writer.closed == 0);
    CHECK(close(ends[0]) == 0);

    CHECK(pipe(ends) == 0);
    FILE *in = fdopen(ends[0], "r"), *out = fdopen(ends[1], "w");
    CHECK(in != NULL && out != NULL);
    CHECK(fputs("native pipe\n", out) >= 0 && fclose(out) == 0);
    char line[32];
    CHECK(fgets(line, sizeof(line), in) == line && strcmp(line, "native pipe\n") == 0);
    CHECK(fgetc(in) == EOF && feof(in) && !ferror(in));
    CHECK(fclose(in) == 0);
    puts("GLIBC_PIPE_THREAD_STDIO_PASS");
    return 0;
}

static int close_on_exec(void)
{
    int ends[2], status;
    pid_t pid;
    char *arguments[] = { "g3_pipe", "child", NULL };
    char *environment[] = { NULL };
    CHECK(pipe(ends) == 0 && ends[0] == 3 && ends[1] == 4);
    CHECK(posix_spawn(&pid, "/bin/g3_pipe", NULL, NULL, arguments, environment) == ENOTSUP);
    CHECK(close(ends[0]) == 0 && close(ends[1]) == 0);
    CHECK(pipe2(ends, O_CLOEXEC) == 0 && ends[0] == 3 && ends[1] == 4);
    CHECK(posix_spawn(&pid, "/bin/g3_pipe", NULL, NULL, arguments, environment) == 0);
    CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(write(ends[1], "p", 1) == 1 && close(ends[1]) == 0);
    char byte;
    CHECK(read(ends[0], &byte, 1) == 1 && byte == 'p' && read(ends[0], &byte, 1) == 0);
    CHECK(close(ends[0]) == 0);
    puts("GLIBC_PIPE_CLOEXEC_PASS");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strcmp(argv[1], "child") == 0) {
        CHECK(fcntl(3, F_GETFD) == -1 && errno == EBADF);
        CHECK(fcntl(4, F_GETFD) == -1 && errno == EBADF);
        return 0;
    }
    CHECK(argc == 1);
    CHECK(nonblocking() == 0);
    CHECK(capacity() == 0);
    CHECK(thread_stdio() == 0);
    CHECK(close_on_exec() == 0);
    return 0;
}
