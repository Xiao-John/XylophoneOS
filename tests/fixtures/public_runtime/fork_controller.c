/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <xos/sleep.h>

#define CHECK(value) do { if (!(value)) { \
    dprintf(2, "DYNAMIC_FORK_FAIL line=%d errno=%d pid=%ld\n", __LINE__, errno, (long)getpid()); return 1; \
} } while (0)
extern char **environ;
static const char *self;
static __thread unsigned tls_value = 31;
static int constructor_result;
struct channel_info { uint32_t version, size, handle, rights; uint64_t peer_pid, controller_pid; };
static long trap(unsigned long call, unsigned long first, unsigned long second, unsigned long third) {
    long result;
    __asm__ volatile("int $0x80" : "=a"(result) : "a"(call), "D"(first), "S"(second), "d"(third) : "memory", "cc");
    return result;
}
__attribute__((constructor)) static void before_ready(void) {
    errno = 0;
    constructor_result = fork() == -1 && errno == EBUSY;
    if (!constructor_result) _Exit(90);
}
static int env_number(const char *name, long value) {
    char text[32];
    CHECK(snprintf(text, sizeof(text), "%ld", value) > 0);
    CHECK(setenv(name, text, 1) == 0); return 0;
}
static long number(const char *name) {
    const char *value = getenv(name); return value ? strtol(value, NULL, 10) : -1;
}
static int pair(uint64_t controller, uint32_t output[2]) {
    unsigned count = 0; output[0] = output[1] = 0;
    for (unsigned i = 0; i < 128; ++i) {
        struct channel_info info = {0};
        long result = trap(81, 1, i, (unsigned long)&info);
        if (result == -15) break;
        CHECK(result == 0 && info.version == 1 && info.size == sizeof(info));
        CHECK(info.controller_pid == controller && info.peer_pid == controller);
        CHECK(info.rights == 1 || info.rights == 2);
        CHECK(output[info.rights - 1] == 0); output[info.rights - 1] = info.handle; ++count;
    }
    CHECK(count == 2 && output[0] && output[1] && output[0] != output[1]); return 0;
}
static int child_identity(pid_t parent, pthread_t old_tid, const uint32_t old_handles[2]) {
    CHECK(getpid() != parent && pthread_self() != old_tid && tls_value == 91);
    struct xos_sleep_ticket ticket;
    CHECK(xos_sleep_query(pthread_self(), &ticket) == ESRCH);
    uint32_t control[2]; CHECK(pair((uint64_t)parent, control) == 0);
    CHECK(control[0] != old_handles[0] && control[1] != old_handles[1]);
    unsigned char bytes[128] = {0};
    CHECK(trap(4, old_handles[0], (unsigned long)bytes, sizeof(bytes)) == -1);
    CHECK(trap(5, old_handles[1], (unsigned long)bytes, sizeof(bytes)) == -1);
    return 0;
}
static int parent_handles(uint32_t output[2]) {
    struct channel_info info = {0};
    CHECK(trap(81, 1, 0, (unsigned long)&info) == 0);
    return pair(info.controller_pid, output);
}
static int finish(pid_t child) {
    int status = -1;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(waitpid(child, &status, WNOHANG) == -1 && errno == ECHILD); return 0;
}
static int after_exec(void) {
    CHECK(getpid() == (pid_t)number("FORK_PID") && tls_value == 31 && constructor_result);
    uint32_t control[2]; CHECK(pair((uint64_t)number("FORK_CONTROLLER"), control) == 0);
    CHECK(fcntl(5, F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(6, F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(9, F_GETFD) == -1 && errno == EBADF);
    char bytes[8];
    CHECK(read(3, bytes, 1) == 1 && bytes[0] == 'B');
    CHECK(read(4, bytes, 1) == 1 && bytes[0] == 'C' && lseek(3, 0, SEEK_CUR) == 3);
    CHECK(read(10, bytes, 2) == 2 && !memcmp(bytes, "DA", 2) && close(10) == 0);
    CHECK(read(11, bytes, 2) == 2 && !memcmp(bytes, "TA", 2));
    CHECK(read(11, bytes, 1) == 0 && close(11) == 0);
    CHECK(fcntl(12, F_SETFL, O_WRONLY | O_NONBLOCK) == 0 && fcntl(13, F_GETFL) == (O_WRONLY | O_NONBLOCK));
    CHECK(write(12, "O", 1) == 1 && close(12) == 0);
    CHECK(write(13, "K", 1) == 1 && close(13) == 0);
    CHECK(close(3) == 0 && close(4) == 0);
    puts("DYNAMIC_FORK_PASS child_exec_pid_fd_alias_cloexec_pipe"); return 0;
}
static int fork_exec(void) {
    CHECK(open("/tests/input", O_RDONLY) == 3 && dup(3) == 4);
    CHECK(open("/tests/input", O_RDONLY | O_CLOEXEC) == 5);
    char byte; CHECK(read(3, &byte, 1) == 1 && byte == 'A');
    int input[2], output[2]; CHECK(pipe2(input, O_CLOEXEC) == 0 && pipe2(output, O_CLOEXEC) == 0);
    CHECK(input[0] == 6 && input[1] == 7 && output[0] == 8 && output[1] == 9);
    CHECK(dup2(6, 10) == 10 && dup2(6, 11) == 11 && dup2(9, 12) == 12 && dup2(9, 13) == 13);
    uint32_t upstream[2]; CHECK(parent_handles(upstream) == 0);
    const pid_t parent = getpid(); const pthread_t tid = pthread_self(); tls_value = 91;
    CHECK(fflush(NULL) == 0);
    pid_t child = fork(); CHECK(child >= 0);
    if (!child) {
        CHECK(child_identity(parent, tid, upstream) == 0);
        CHECK(close(7) == 0 && close(8) == 0);
        CHECK(env_number("FORK_PID", (long)getpid()) == 0 && env_number("FORK_CONTROLLER", parent) == 0);
        char *large = malloc(4097); CHECK(large); memset(large, 'x', 4096); large[4096] = 0;
        char *invalid[] = {(char *)self, large, NULL};
        const pid_t before = getpid(); errno = 0;
        CHECK(execve(self, invalid, environ) == -1 && errno == E2BIG && getpid() == before);
        CHECK(lseek(3, 0, SEEK_CUR) == 1 && fcntl(5, F_GETFD) == FD_CLOEXEC);
        free(large); puts("DYNAMIC_FORK_PASS failed_exec_retains_control_pid_fds");
        char *next[] = {(char *)self, "replaced", NULL}; execve(self, next, environ); CHECK(0);
    }
    CHECK(close(6) == 0 && close(9) == 0);
    for (int fd = 10; fd <= 13; ++fd) CHECK(close(fd) == 0);
    CHECK(write(7, "DATA", 4) == 4 && close(7) == 0);
    CHECK(finish(child) == 0); /* Public wait drives this parent's new controller. */
    char result[2]; CHECK(read(8, result, 2) == 2 && !memcmp(result, "OK", 2));
    CHECK(read(8, result, 1) == 0 && close(8) == 0);
    CHECK(getpid() == parent && pthread_self() == tid && tls_value == 91);
    CHECK(read(3, &byte, 1) == 1 && byte == 'D' && fcntl(5, F_GETFD) == FD_CLOEXEC);
    CHECK(close(3) == 0 && close(4) == 0 && close(5) == 0);
    uint32_t retained[2]; CHECK(parent_handles(retained) == 0 && retained[0] == upstream[0] && retained[1] == upstream[1]);
    puts("DYNAMIC_FORK_PASS parent_wait_owner_and_resources"); return 0;
}
static int nested(void) {
    const pid_t parent = getpid(); const pthread_t tid = pthread_self(); tls_value = 91;
    uint32_t original[2]; CHECK(parent_handles(original) == 0);
    pid_t child = fork(); CHECK(child >= 0);
    if (!child) {
        CHECK(child_identity(parent, tid, original) == 0);
        const pid_t controller = getpid(); uint32_t fresh[2]; CHECK(pair((uint64_t)parent, fresh) == 0);
        const pthread_t child_tid = pthread_self();
        pid_t grandchild = fork(); CHECK(grandchild >= 0);
        if (!grandchild) {
            CHECK(child_identity(controller, child_tid, fresh) == 0);
            CHECK(env_number("FORK_PID", (long)getpid()) == 0 && env_number("FORK_CONTROLLER", controller) == 0);
            char *next[] = {(char *)self, "nested-replaced", NULL}; execve(self, next, environ); CHECK(0);
        }
        CHECK(finish(grandchild) == 0); return 0;
    }
    CHECK(finish(child) == 0); puts("DYNAMIC_FORK_PASS nested_controller_chain"); return 0;
}
static int owner_exit(void) {
    CHECK(open("/tests/input", O_RDONLY) == 3);
    int pipes[2]; CHECK(pipe2(pipes, O_NONBLOCK) == 0);
    pid_t child = fork(); CHECK(child >= 0);
    if (!child) {
        /* Separate completed adoption from loss of a controller while the
           READY_ACK is still in flight.  This byte proves fork returned. */
        CHECK(write(pipes[1], "R", 1) == 1);
        const pid_t before = getpid();
        const long deadline = trap(46, 0, 0, 0) + 5000000000L;
        for (;;) {
            struct channel_info info = {0};
            const long observed = trap(81, 1, 0, (unsigned long)&info);
            if (observed == -15) break;
            CHECK(observed == 0 && trap(46, 0, 0, 0) < deadline && sched_yield() == 0);
        }
        CHECK(fork() == -1 && errno == EPERM);
        char *next[] = {(char *)self, "must-not-run", NULL};
        CHECK(execve(self, next, environ) == -1 && errno == EPERM && getpid() == before);
        char byte; CHECK(read(3, &byte, 1) == 1 && byte == 'A');
        CHECK(write(pipes[1], "Z", 1) == 1 && read(pipes[0], &byte, 1) == 1 && byte == 'Z');
        CHECK(close(3) == 0 && close(pipes[0]) == 0 && close(pipes[1]) == 0);
        puts("DYNAMIC_FORK_PASS dead_controller_denies_without_fd_or_pid_loss"); return 0;
    }
    const long deadline = trap(46, 0, 0, 0) + 5000000000L;
    for (;;) {
        char ready = 0;
        const ssize_t received = read(pipes[0], &ready, 1);
        if (received == 1) { CHECK(ready == 'R'); break; }
        int status = -1;
        CHECK(received == -1 && errno == EAGAIN && waitpid(child, &status, WNOHANG) == 0);
        CHECK(trap(46, 0, 0, 0) < deadline && sched_yield() == 0);
    }
    puts("DYNAMIC_FORK_PASS controller_child_adopted_before_exit");
    puts("DYNAMIC_FORK_PASS controller_normal_exit"); return 0;
}
static void *worker(void *value) { return value; }
int main(int argc, char **argv) {
    CHECK(argc == 2 && constructor_result); self = argv[0];
    if (!strcmp(argv[1], "replaced")) return after_exec();
    if (!strcmp(argv[1], "fork-exec")) return fork_exec();
    if (!strcmp(argv[1], "nested")) return nested();
    if (!strcmp(argv[1], "nested-replaced")) {
        uint32_t control[2];
        CHECK(getpid() == (pid_t)number("FORK_PID") && pair((uint64_t)number("FORK_CONTROLLER"), control) == 0);
        puts("DYNAMIC_FORK_PASS nested_same_pid_exec"); return 0;
    }
    if (!strcmp(argv[1], "owner-exit")) return owner_exit();
    if (!strcmp(argv[1], "owner-kill")) {
        int pipes[2]; CHECK(pipe(pipes) == 0 && open("/tests/input", O_RDONLY) >= 3);
        pid_t child = fork(); CHECK(child >= 0);
        if (child) { printf("DYNAMIC_FORK_KILL_READY parent=%ld child=%ld\n", (long)getpid(), (long)child); fflush(stdout); }
        for (;;) { const struct timespec delay = {1, 0}; CHECK(nanosleep(&delay, NULL) == 0); }
    }
    if (!strcmp(argv[1], "threads")) {
        /* This exact C-only closure has no libgcc_s unwinder.  pthread_create
           opts into the native thread profile, then rejects before reserving
           a worker.  The profile itself permanently closes fork admission. */
        pthread_t thread = (pthread_t)-1;
        CHECK(pthread_create(&thread, NULL, worker, NULL) == ENOTSUP && thread == (pthread_t)-1);
        CHECK(fork() == -1 && errno == ENOTSUP && _Fork() == -1 && errno == ENOTSUP);
        puts("DYNAMIC_FORK_PASS thread_profile_rejected"); return 0;
    }
    if (!strcmp(argv[1], "authority")) {
        CHECK(env_number("FORK_PID", (long)getpid()) == 0);
        CHECK(trap(87, (unsigned long)getpid(), 3, 0) == 0);
        CHECK(fork() == -1 && errno == EPERM);
        char *next[] = {(char *)self, "authority-replaced", NULL}; execve(self, next, environ); CHECK(0);
    }
    CHECK(!strcmp(argv[1], "authority-replaced"));
    CHECK(getpid() == (pid_t)number("FORK_PID") && trap(87, (unsigned long)getpid(), 3, 0) == 0);
    CHECK(fork() == -1 && errno == EPERM);
    puts("DYNAMIC_FORK_PASS denied_fork_same_pid_exec_no_authority_gain"); return 0;
}
