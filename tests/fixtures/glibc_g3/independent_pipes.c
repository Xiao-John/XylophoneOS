/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define CHECK(value) do { if (!(value)) { \
    dprintf(2, "INDEPENDENT_PIPE_FAIL line=%d errno=%d\n", __LINE__, errno); return 1; \
} } while (0)
static const char *self;
static const char *closed_path = "/data/independent_closed";
static const char *gate_path = "/data/independent_gate";
static long long now(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return -1;
    return (long long)value.tv_sec * 1000000000LL + value.tv_nsec;
}
static int mark(const char *path) {
    int fd = open(path, O_CREAT | O_EXCL | O_WRONLY, 0600);
    return fd < 0 ? -1 : close(fd);
}
static int wait_gate(void) {
    const long long deadline = now() + 5000000000LL;
    CHECK(mark(closed_path) == 0);
    while (access(gate_path, F_OK)) {
        CHECK(errno == ENOENT && now() < deadline && sched_yield() == 0);
    }
    return 0;
}
static int finish(pid_t pid) {
    int status = 0;
    CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(waitpid(pid, &status, WNOHANG) == -1 && errno == ECHILD);
    return 0;
}
static int release(pid_t pid) {
    int status = 4567;
    const long long deadline = now() + 5000000000LL;
    while (access(closed_path, F_OK)) {
        CHECK(errno == ENOENT && now() < deadline && sched_yield() == 0);
    }
    CHECK(waitpid(pid, &status, WNOHANG) == 0 && status == 4567);
    CHECK(mark(gate_path) == 0 && finish(pid) == 0);
    CHECK(unlink(closed_path) == 0 && unlink(gate_path) == 0);
    return 0;
}
static int launch(pid_t *pid, const char *mode) {
    char *argv[] = {(char *)self, (char *)mode, NULL}; char *envp[] = {NULL};
    return posix_spawn(pid, self, NULL, NULL, argv, envp);
}
static int child_io(int broken) {
    CHECK(fcntl(12, F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(13, F_GETFD) == -1 && errno == EBADF);
    struct stat info;
    CHECK(fstat(8, &info) == 0 && S_ISFIFO(info.st_mode));
    CHECK(fstat(10, &info) == 0 && S_ISFIFO(info.st_mode));
    CHECK(fcntl(8, F_SETFL, O_RDONLY | O_NONBLOCK) == 0);
    CHECK(fcntl(9, F_GETFL) == (O_RDONLY | O_NONBLOCK));
    CHECK(fcntl(8, F_SETFL, O_RDONLY) == 0);
    CHECK(fcntl(10, F_SETFL, O_WRONLY | O_NONBLOCK) == 0);
    CHECK(fcntl(11, F_GETFL) == (O_WRONLY | O_NONBLOCK));
    CHECK(fcntl(10, F_SETFL, O_WRONLY) == 0);
    char bytes[4];
    CHECK(write(8, "X", 1) == -1 && errno == EBADF);
    CHECK(read(10, bytes, 1) == -1 && errno == EBADF);
    CHECK(read(8, bytes, 2) == 2 && !memcmp(bytes, "AB", 2));
    CHECK(close(8) == 0);
    CHECK(read(9, bytes, 2) == 2 && !memcmp(bytes, "CD", 2));
    CHECK(read(9, bytes, 1) == 0 && close(9) == 0);
    if (broken) {
        CHECK(wait_gate() == 0);
        CHECK(write(10, "X", 1) == -1 && errno == EPIPE);
        CHECK(close(10) == 0 && close(11) == 0);
        return 0;
    }
    CHECK(write(10, "OUT", 3) == 3 && close(10) == 0);
    CHECK(write(11, "ALIAS", 5) == 5 && close(11) == 0);
    return wait_gate();
}
static int aliases(const char *mode) {
    int input[2], output[2];
    CHECK(pipe2(input, O_CLOEXEC) == 0 && pipe2(output, O_CLOEXEC) == 0);
    CHECK(dup2(input[0], 8) == 8 && dup2(input[0], 9) == 9);
    CHECK(dup2(output[1], 10) == 10 && dup2(output[1], 11) == 11);
    CHECK(fcntl(input[0], F_DUPFD_CLOEXEC, 12) == 12);
    CHECK(fcntl(output[1], F_DUPFD_CLOEXEC, 13) == 13);
    pid_t pid = -1;
    CHECK(launch(&pid, mode) == 0 && pid > 0);
    for (int fd = 8; fd <= 13; ++fd) CHECK(close(fd) == 0);
    CHECK(close(input[0]) == 0 && close(output[1]) == 0);
    CHECK(write(input[1], "ABCD", 4) == 4 && close(input[1]) == 0);
    if (!strcmp(mode, "broken")) {
        CHECK(close(output[0]) == 0 && release(pid) == 0);
        return 0;
    }
    CHECK(fcntl(output[0], F_SETFL, O_RDONLY | O_NONBLOCK) == 0);
    char bytes[16]; size_t length = 0;
    const long long deadline = now() + 5000000000LL;
    for (;;) {
        ssize_t count = read(output[0], bytes + length, sizeof(bytes) - length);
        if (!count) break;
        if (count < 0) CHECK(errno == EAGAIN && now() < deadline && sched_yield() == 0);
        else { length += (size_t)count; CHECK(length < sizeof(bytes)); }
    }
    CHECK(length == 8 && !memcmp(bytes, "OUTALIAS", 8));
    CHECK(close(output[0]) == 0 && release(pid) == 0);
    return 0;
}
static int capacity_child(void) {
    for (int fd = 3; fd <= 18; ++fd) {
        struct stat info; CHECK(fstat(fd, &info) == 0 && S_ISFIFO(info.st_mode));
    }
    CHECK(fcntl(3, F_SETFL, O_RDONLY | O_NONBLOCK) == 0);
    for (int fd = 19; fd < 32; ++fd) CHECK(fcntl(fd, F_GETFL) == (O_RDONLY | O_NONBLOCK));
    CHECK(fcntl(3, F_SETFL, O_RDONLY) == 0);
    CHECK(fcntl(3, F_DUPFD, 0) == -1 && errno == EMFILE);
    for (int fd = 19; fd < 32; ++fd) CHECK(close(fd) == 0);
    for (int index = 0; index < 8; ++index) {
        char byte = (char)('A' + index), result = 0;
        const int reader = 3 + 2 * index, writer = reader + 1;
        CHECK(write(writer, &byte, 1) == 1 && read(reader, &result, 1) == 1 && result == byte);
        CHECK(close(reader) == 0 && close(writer) == 0);
    }
    return 0;
}
static int capacity(void) {
    int handles[8][2];
    for (int index = 0; index < 8; ++index) {
        CHECK(pipe(handles[index]) == 0);
        CHECK(handles[index][0] == 3 + 2 * index && handles[index][1] == 4 + 2 * index);
    }
    int untouched[2] = {-123, -456};
    CHECK(pipe(untouched) == -1 && errno == ENFILE && untouched[0] == -123 && untouched[1] == -456);
    for (int fd = 19; fd < 32; ++fd) CHECK(dup2(3, fd) == fd);
    pid_t pid = -1; CHECK(launch(&pid, "capacity-child") == 0);
    for (int fd = 3; fd < 32; ++fd) CHECK(close(fd) == 0);
    CHECK(finish(pid) == 0);
    CHECK(pipe(untouched) == 0 && close(untouched[0]) == 0 && close(untouched[1]) == 0);
    return 0;
}
int main(int argc, char **argv) {
    CHECK(argc > 0 && argv[0] && argv[0][0] == '/'); self = argv[0];
    if (argc == 3 && !strcmp(argv[1], "after-exec")) {
        CHECK(getpid() == (pid_t)strtol(argv[2], NULL, 10));
        puts("INDEPENDENT_PIPE_PASS same_pid_exec");
        return child_io(0);
    }
    if (argc == 2) {
        if (!strcmp(argv[1], "aliases")) return child_io(0);
        if (!strcmp(argv[1], "broken")) return child_io(1);
        if (!strcmp(argv[1], "capacity-child")) return capacity_child();
        CHECK(!strcmp(argv[1], "exec"));
        char pid[32]; CHECK(snprintf(pid, sizeof(pid), "%ld", (long)getpid()) > 0);
        char *next[] = {(char *)self, "after-exec", pid, NULL}; char *environment[] = {NULL};
        errno = 0; CHECK(execve("/bin/no-independent-image", next, environment) == -1 && errno == ENOENT);
        CHECK(fcntl(8, F_GETFD) == 0 && fcntl(11, F_GETFD) == 0);
        execve(self, next, environment); CHECK(0);
    }
    CHECK(argc == 1);
    CHECK(aliases("aliases") == 0);
    puts("INDEPENDENT_PIPE_PASS independent_alias_flags_cloexec_eof_before_exit");
    CHECK(aliases("exec") == 0);
    puts("INDEPENDENT_PIPE_PASS failed_and_successful_exec_parent_preserved");
    CHECK(aliases("broken") == 0);
    puts("INDEPENDENT_PIPE_PASS independent_reader_close_epipe");
    CHECK(capacity() == 0);
    puts("INDEPENDENT_PIPE_PASS eight_objects_sixteen_references_thirtytwo_descriptors");
    puts("INDEPENDENT_PIPE_OK cases=4"); return 0;
}
