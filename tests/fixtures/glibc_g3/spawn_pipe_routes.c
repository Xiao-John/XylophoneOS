/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define CHECK(value) do { if (!(value)) { \
    dprintf(2, "SPAWN_PIPE_FAIL line=%d errno=%d\n", __LINE__, errno); return 1; \
} } while (0)
static const char *self = "/tests/spawn_pipe.elf";
static const char *closed_path = "/data/spawn_pipe_closed";
static const char *gate_path = "/data/spawn_pipe_gate";
static int spawn(pid_t *, const char *);
static int finish(pid_t);

static long long now(void)
{
    struct timespec time;
    if (clock_gettime(CLOCK_MONOTONIC, &time)) return -1;
    return (long long)time.tv_sec * 1000000000LL + time.tv_nsec;
}

static int mark(const char *path)
{
    int fd = open(path, O_CREAT | O_EXCL | O_WRONLY, 0600);
    return fd < 0 ? -1 : close(fd);
}

static int wait_gate(void)
{
    long long end = now() + 5000000000LL;
    CHECK(mark(closed_path) == 0);
    while (access(gate_path, F_OK)) {
        CHECK(errno == ENOENT && now() < end);
        CHECK(sched_yield() == 0);
    }
    return 0;
}

static int child(const char *mode)
{
    CHECK(fcntl(9, F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(20, F_GETFD) == -1 && errno == EBADF);
    if (!strcmp(mode, "kernel-extra-read")) {
        CHECK(fcntl(0, F_GETFD) == -1 && errno == EBADF);
        CHECK(fcntl(8, F_GETFL) == O_RDONLY);
        char bytes[2];
        CHECK(read(8, bytes, 2) == 2 && !memcmp(bytes, "DA", 2));
        CHECK(close(8) == 0);
        return 0;
    }
    if (!strcmp(mode, "kernel-extra")) {
        CHECK(fcntl(1, F_GETFD) == -1 && errno == EBADF);
        CHECK(fcntl(8, F_GETFL) == O_WRONLY);
        CHECK(write(8, "SPAWN_PIPE_EXTRA_KERNEL_OK\n", 27) == 27);
        CHECK(close(8) == 0);
        return 0;
    }
    if (!strcmp(mode, "broken")) {
        CHECK(wait_gate() == 0);
        CHECK(write(1, "X", 1) == -1 && errno == EPIPE);
        CHECK(close(1) == 0);
        return 0;
    }
    CHECK(!strcmp(mode, "aliases"));
    struct stat info;
    CHECK(fstat(0, &info) == 0 && S_ISFIFO(info.st_mode));
    CHECK(fstat(7, &info) == 0 && S_ISFIFO(info.st_mode));
    CHECK(fcntl(7, F_GETFD) == 0 && fcntl(8, F_GETFD) == 0);
    CHECK(fcntl(7, F_SETFL, O_WRONLY | O_NONBLOCK) == 0);
    CHECK(fcntl(1, F_GETFL) == (O_WRONLY | O_NONBLOCK));
    CHECK(fcntl(2, F_GETFL) == (O_WRONLY | O_NONBLOCK));
    CHECK(fcntl(7, F_SETFL, O_WRONLY) == 0);
    char bytes[4];
    CHECK(close(0) == 0);
    /* The first spawn translated the pipe into a kernel route. A second
       ordinary spawn must retain its extra FD after the POSIX fd0 is closed. */
    pid_t nested = -1;
    CHECK(spawn(&nested, "kernel-extra-read") == 0 && finish(nested) == 0);
    CHECK(read(8, bytes, 2) == 2 && !memcmp(bytes, "TA", 2));
    CHECK(read(8, bytes, 1) == 0 && close(8) == 0);
    CHECK(write(1, "OUT", 3) == 3 && close(1) == 0);
    CHECK(write(2, "ERR", 3) == 3 && close(2) == 0);
    CHECK(write(7, "ALIAS", 5) == 5 && close(7) == 0);
    /* Keep this process alive: EOF must follow last close, not process exit. */
    return wait_gate();
}

static int spawn(pid_t *pid, const char *mode)
{
    char *argv[] = { (char *)self, (char *)mode, NULL };
    char *envp[] = { NULL };
    return posix_spawn(pid, self, NULL, NULL, argv, envp);
}

static int finish(pid_t pid)
{
    int status = 0;
    CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(waitpid(pid, &status, WNOHANG) == -1 && errno == ECHILD);
    return 0;
}

static int release(pid_t pid)
{
    int status = 1234;
    long long end = now() + 5000000000LL;
    while (access(closed_path, F_OK)) {
        CHECK(errno == ENOENT && now() < end);
        CHECK(sched_yield() == 0);
    }
    CHECK(waitpid(pid, &status, WNOHANG) == 0 && status == 1234);
    CHECK(mark(gate_path) == 0 && finish(pid) == 0);
    CHECK(unlink(closed_path) == 0 && unlink(gate_path) == 0);
    return 0;
}

int main(int argc, char **argv)
{
    CHECK(argc > 0 && argv[0] != NULL && argv[0][0] == '/');
    self = argv[0];
    if (argc == 2) return child(argv[1]);
    CHECK(argc == 1);
    int saved[3];
    for (int fd = 0; fd < 3; ++fd) {
        saved[fd] = fcntl(fd, F_DUPFD_CLOEXEC, 20);
        CHECK(saved[fd] == 20 + fd);
    }
    int input[2], output[2];
    CHECK(pipe2(input, O_CLOEXEC) == 0 && pipe2(output, O_CLOEXEC) == 0);
    CHECK(dup2(input[0], 0) == 0 && dup2(input[0], 8) == 8);
    CHECK(dup2(output[1], 1) == 1 && dup2(output[1], 2) == 2);
    CHECK(dup2(output[1], 7) == 7 && fcntl(output[1], F_DUPFD_CLOEXEC, 9) == 9);
    pid_t pid = -1;
    CHECK(spawn(&pid, "aliases") == 0 && pid > 0);
    for (int fd = 0; fd < 3; ++fd) CHECK(dup2(saved[fd], fd) == fd);
    CHECK(close(input[0]) == 0 && close(output[1]) == 0);
    CHECK(close(7) == 0 && close(8) == 0 && close(9) == 0);
    CHECK(write(input[1], "DATA", 4) == 4 && close(input[1]) == 0);
    CHECK(fcntl(output[0], F_SETFL, O_RDONLY | O_NONBLOCK) == 0);
    char bytes[32]; size_t length = 0;
    long long end = now() + 5000000000LL;
    for (;;) {
        ssize_t count = read(output[0], bytes + length, sizeof(bytes) - length);
        if (!count) break;
        if (count < 0) { CHECK(errno == EAGAIN && now() < end); CHECK(sched_yield() == 0); }
        else { length += (size_t)count; CHECK(length < sizeof(bytes)); }
    }
    CHECK(length == 11 && !memcmp(bytes, "OUTERRALIAS", 11));
    CHECK(close(output[0]) == 0 && release(pid) == 0);
    puts("SPAWN_PIPE_PASS routed_read_write_alias_flags_cloexec_eof_before_exit");

    CHECK(dup2(1, 8) == 8 && close(1) == 0);
    CHECK(spawn(&pid, "kernel-extra") == 0);
    CHECK(dup2(saved[1], 1) == 1 && close(8) == 0 && finish(pid) == 0);
    puts("SPAWN_PIPE_PASS kernel_extra_alias_after_original_stdio_close");

    CHECK(pipe(input) == 0);
    pid = -777;
    CHECK(spawn(&pid, "aliases") == ENOTSUP && pid == -777);
    CHECK(write(input[1], "P", 1) == 1 && close(input[1]) == 0);
    CHECK(read(input[0], bytes, 1) == 1 && bytes[0] == 'P');
    CHECK(read(input[0], bytes, 1) == 0 && close(input[0]) == 0);
    puts("SPAWN_PIPE_PASS unrouted_pipe_explicit_rejection_parent_preserved");

    CHECK(pipe2(output, O_CLOEXEC) == 0 && dup2(output[1], 1) == 1);
    CHECK(spawn(&pid, "broken") == 0);
    CHECK(dup2(saved[1], 1) == 1);
    CHECK(close(output[0]) == 0 && close(output[1]) == 0 && release(pid) == 0);
    puts("SPAWN_PIPE_PASS closed_reader_epipe");
    for (int fd = 0; fd < 3; ++fd) CHECK(close(saved[fd]) == 0);
    puts("SPAWN_PIPE_OK cases=4");
    return 0;
}
