/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <termios.h>
#include <unistd.h>
#include "terminal_owner_evidence.h"

struct packet { uint64_t kind, value; };
static int packet(uint64_t kind, uint64_t value) {
    const struct packet message = {kind, value};
    return write(3, &message, sizeof(message)) == sizeof(message);
}
#define CHECK(value) do { if (!(value)) { \
    const int error = errno; (void)packet(4, ((uint64_t)__LINE__ << 32) | (unsigned)error); \
    dprintf(2, "DYNAMIC_TERMINAL_FAIL line=%d errno=%d pid=%ld\n", __LINE__, error, (long)getpid()); return 1; \
} } while (0)
extern char **environ;
static const char *self;
static uint64_t monotonic_ns(void);
static __thread unsigned tls_value = 37;
static int constructor_ready;
struct channel_info { uint32_t version, size, handle, rights; uint64_t peer_pid, controller_pid; };
struct identity {
    uint64_t pid, authority, owner, service, controller;
    uint32_t terminal_send, terminal_receive, ready, ack;
};
static long trap(unsigned long call, unsigned long first, unsigned long second, unsigned long third) {
    long result;
    __asm__ volatile("int $0x80" : "=a"(result) : "a"(call), "D"(first), "S"(second), "d"(third) : "memory", "cc");
    return result;
}
__attribute__((constructor)) static void before_ready(void) {
    struct termios mode;
    constructor_ready = isatty(0) && isatty(1) && isatty(2) && tcgetattr(0, &mode) == 0;
    if (!constructor_ready) _Exit(90);
}
static int identify(struct identity *output, int has_controller) {
    memset(output, 0, sizeof(*output));
    output->pid = (uint64_t)getpid();
    const long authority = trap(87, (unsigned long)output->pid, 3, 0);
    CHECK(authority == 0 || authority == 1); output->authority = (uint64_t)authority;
    unsigned terminal_count = 0, control_count = 0;
    for (unsigned ordinal = 0; ordinal < 32; ++ordinal) {
        struct channel_info info = {0};
        const long result = trap(81, 1, ordinal, (unsigned long)&info);
        if (result == -15) break;
        CHECK(result == 0 && info.version == 1 && info.size == sizeof(info));
        CHECK(info.rights == 1 || info.rights == 2);
        if (info.peer_pid == info.controller_pid) {
            CHECK(has_controller && (!output->controller || output->controller == info.controller_pid));
            output->controller = info.controller_pid;
            uint32_t *slot = info.rights == 1 ? &output->ready : &output->ack;
            CHECK(!*slot); *slot = info.handle; ++control_count;
        } else {
            CHECK((!output->owner || output->owner == info.controller_pid) &&
                  (!output->service || output->service == info.peer_pid));
            output->owner = info.controller_pid; output->service = info.peer_pid;
            uint32_t *slot = info.rights == 1 ? &output->terminal_send : &output->terminal_receive;
            CHECK(!*slot); *slot = info.handle; ++terminal_count;
        }
    }
    CHECK(terminal_count == 2 && control_count == (has_controller ? 2u : 0u));
    CHECK(output->owner && output->service && output->terminal_send && output->terminal_receive);
    return 0;
}
static int same_identity(const struct identity *before) {
    struct identity after; CHECK(identify(&after, 1) == 0);
    CHECK(memcmp(before, &after, sizeof(after)) == 0); return 0;
}
static int wait_child(pid_t child) {
    int status = -1;
    CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    CHECK(waitpid(child, &status, WNOHANG) == -1 && errno == ECHILD); return 0;
}
static int after_exec(const char *encoded, const char *mode_name, const char *timing) {
    const uint64_t entered = monotonic_ns();
    uint64_t failed_elapsed = 0, exec_started = 0;
    CHECK(sscanf(timing, "%lu,%lu", &failed_elapsed, &exec_started) == 2 &&
          exec_started && entered >= exec_started);
    struct identity before = {0};
    CHECK(sscanf(encoded, "%lu,%lu,%lu,%lu,%lu,%u,%u,%u,%u", &before.pid, &before.authority,
        &before.owner, &before.service, &before.controller, &before.terminal_send,
        &before.terminal_receive, &before.ready, &before.ack) == 9);
    CHECK(constructor_ready && tls_value == 37 && same_identity(&before) == 0);
    CHECK(fcntl(7, F_GETFD) == -1 && errno == EBADF);
    CHECK(fcntl(8, F_GETFD) == -1 && errno == EBADF && isatty(9));
    CHECK(dprintf(9, "DYNAMIC_TERMINAL_NEW_MAIN %s pid=%ld failed_exec_ns=%lu exec_ns=%lu\n",
        mode_name, (long)getpid(), (unsigned long)failed_elapsed,
        (unsigned long)(entered - exec_started)) > 0);
    CHECK(failed_elapsed < 30000000000ULL && entered - exec_started < 30000000000ULL);
    char byte = 0;
    CHECK(read(5, &byte, 1) == 1 && byte == 'B');
    CHECK(read(6, &byte, 1) == 1 && byte == 'C' && lseek(5, 0, SEEK_CUR) == 3);
    CHECK(close(11) == 0 && read(10, &byte, 1) == 1 && byte == 'P' && read(10, &byte, 1) == 0);
    struct termios mode; CHECK(tcgetattr(9, &mode) == 0 && mode.c_cc[VMIN] == 0 && mode.c_cc[VTIME] == 20);
    if (!strcmp(mode_name, "authority")) {
        errno = 0; CHECK(before.authority == 0 && fork() == -1 && errno == EPERM);
    }
    CHECK(dprintf(9, "DYNAMIC_TERMINAL_INPUT_READY %s\n", mode_name) > 0);
    CHECK(read(0, &byte, 1) == 1 && byte == 'T');
    CHECK(dprintf(9, "DYNAMIC_TERMINAL_PASS %s pid=%ld\n", mode_name, (long)getpid()) > 0);
    CHECK(packet(3, (uint64_t)getpid())); return 0;
}
static int replace(const char *mode_name) {
    struct identity before; CHECK(identify(&before, 1) == 0);
    char large[4097]; memset(large, 'x', sizeof(large) - 1); large[sizeof(large) - 1] = 0;
    char *invalid[] = {(char *)self, large, NULL};
    const uint64_t failed_started = monotonic_ns();
    errno = 0; CHECK(execve(self, invalid, environ) == -1 && errno == E2BIG);
    const uint64_t failed_elapsed = monotonic_ns() - failed_started;
    CHECK(same_identity(&before) == 0 && fcntl(7, F_GETFD) == FD_CLOEXEC &&
          fcntl(8, F_GETFD) == FD_CLOEXEC && isatty(9) && lseek(5, 0, SEEK_CUR) == 1);
    CHECK(dprintf(9, "DYNAMIC_TERMINAL_FAILED_EXEC_PRESERVED %s\n", mode_name) > 0);
    char encoded[224];
    const int length = snprintf(encoded, sizeof(encoded), "%lu,%lu,%lu,%lu,%lu,%u,%u,%u,%u",
        before.pid, before.authority, before.owner, before.service, before.controller,
        before.terminal_send, before.terminal_receive, before.ready, before.ack);
    CHECK(length > 0 && (size_t)length < sizeof(encoded));
    char timing[64];
    const int timing_length = snprintf(timing, sizeof(timing), "%lu,%lu",
        (unsigned long)failed_elapsed, (unsigned long)monotonic_ns());
    CHECK(timing_length > 0 && (size_t)timing_length < sizeof(timing));
    char *next[] = {(char *)self, "after", encoded, (char *)mode_name, timing, NULL};
    execve(self, next, environ); CHECK(0);
}
static int positive(const char *mode_name) {
    CHECK(open("/tests/terminal_input", O_RDONLY) == 5 && dup(5) == 6 && dup(5) == 7);
    CHECK(fcntl(7, F_SETFD, FD_CLOEXEC) == 0 && dup(1) == 8 && dup(1) == 9);
    CHECK(fcntl(8, F_SETFD, FD_CLOEXEC) == 0);
    int pipe_fds[2]; CHECK(pipe(pipe_fds) == 0 && pipe_fds[0] == 10 && pipe_fds[1] == 11);
    CHECK(write(11, "P", 1) == 1);
    char byte; CHECK(read(5, &byte, 1) == 1 && byte == 'A');
    struct termios mode; CHECK(tcgetattr(0, &mode) == 0);
    mode.c_cc[VMIN] = 0; mode.c_cc[VTIME] = 20; CHECK(tcsetattr(0, TCSANOW, &mode) == 0);
    tls_value = 99;
    if (!strcmp(mode_name, "authority")) {
        errno = 0; CHECK(trap(87, (unsigned long)getpid(), 3, 0) == 0 && fork() == -1 && errno == EPERM);
    }
    if (!strcmp(mode_name, "fork")) {
        struct identity parent; CHECK(identify(&parent, 1) == 0);
        const pid_t child = fork(); CHECK(child >= 0);
        if (!child) {
            struct identity current; CHECK(identify(&current, 1) == 0 && tls_value == 99);
            CHECK(current.pid != parent.pid && current.owner == parent.owner &&
                  current.service == parent.service && current.controller == parent.pid &&
                  current.controller != current.owner && current.terminal_send != parent.terminal_send &&
                  current.ready != parent.ready);
            char denied = 0;
            CHECK(trap(4, parent.terminal_send, (unsigned long)&denied, 1) == -1 &&
                  trap(5, parent.terminal_receive, (unsigned long)&denied, 1) == -1 &&
                  trap(4, parent.ready, (unsigned long)&denied, 1) == -1 &&
                  trap(5, parent.ack, (unsigned long)&denied, 1) == -1);
            return replace(mode_name);
        }
        CHECK(close(10) == 0 && close(11) == 0 && wait_child(child) == 0);
        CHECK(same_identity(&parent) == 0 && tls_value == 99 && read(5, &byte, 1) == 1 && byte == 'D');
        CHECK(dprintf(1, "DYNAMIC_TERMINAL_FORK_PARENT_PRESERVED\n") > 0); return 0;
    }
    return replace(mode_name);
}
static int actor_death(void) {
    CHECK(open("/tests/terminal_input", O_RDONLY) == 5);
    const pid_t before = getpid(); CHECK(packet(1, (uint64_t)before));
    char byte; CHECK(read(4, &byte, 1) == 1 && byte == 'G');
    errno = 0; CHECK(write(1, "lost", 4) == -1 && errno == EPIPE);
    char *next[] = {(char *)self, "unexpected", NULL};
    errno = 0; CHECK(execve(self, next, environ) == -1 && errno == EIO && getpid() == before);
    CHECK(read(5, &byte, 1) == 1 && byte == 'A' && packet(3, (uint64_t)getpid())); return 0;
}
static int owner_exit(void) {
    CHECK(open("/tests/terminal_input", O_RDONLY) == 5);
    int adopted[2]; CHECK(pipe2(adopted, O_NONBLOCK) == 0);
    const pid_t child = fork(); CHECK(child >= 0);
    if (child) {
        CHECK(close(adopted[1]) == 0);
        const long deadline = trap(46, 0, 0, 0) + 5000000000L;
        for (;;) {
            char ready = 0;
            const ssize_t received = read(adopted[0], &ready, 1);
            if (received == 1) { CHECK(ready == 'R'); break; }
            int status = -1;
            CHECK(received == -1 && errno == EAGAIN && waitpid(child, &status, WNOHANG) == 0);
            CHECK(trap(46, 0, 0, 0) < deadline && sched_yield() == 0);
        }
        CHECK(close(adopted[0]) == 0 && packet(2, (uint64_t)child)); return 0;
    }
    /* The separate controller-death check starts only after the child has
       consumed READY_ACK and returned from fork. */
    struct identity before; CHECK(identify(&before, 1) == 0);
    CHECK(close(adopted[0]) == 0 && write(adopted[1], "R", 1) == 1 && close(adopted[1]) == 0);
    char byte; CHECK(read(4, &byte, 1) == 1 && byte == 'G');
    /* The existing actor ends a foreground group when its root application
       exits. Its owner and actor processes survive; this child loses both
       that group and its separate direct-parent launch controller. */
    const long deadline = trap(46, 0, 0, 0) + 5000000000L;
    for (;;) {
        struct channel_info info = {0};
        const long result = trap(81, 1, 0, (unsigned long)&info);
        if (result == -15) break;
        CHECK(result == 0 && trap(46, 0, 0, 0) < deadline && sched_yield() == 0);
    }
    CHECK(trap(4, before.terminal_send, (unsigned long)&byte, 1) == -1 &&
          trap(5, before.terminal_receive, (unsigned long)&byte, 1) == -1);
    errno = 0; CHECK(write(1, "lost", 4) == -1 && errno == EPIPE);
    CHECK(getpid() == (pid_t)before.pid && trap(87, before.pid, 3, 0) == (long)before.authority);
    errno = 0; CHECK(fork() == -1 && errno == EPERM);
    char *next[] = {(char *)self, "unexpected", NULL};
    errno = 0; CHECK(execve(self, next, environ) == -1 && errno == EIO && getpid() == (pid_t)before.pid);
    CHECK(read(5, &byte, 1) == 1 && byte == 'A');
    CHECK(packet(3, (uint64_t)getpid())); return 0;
}
static int owner_kill(void) {
    CHECK(open("/tests/terminal_input", O_RDONLY) == 5);
    const pid_t child = fork(); CHECK(child >= 0);
    if (child) CHECK(packet(2, (uint64_t)child));
    for (;;) sched_yield();
}
/* The owner of both real terminal pairs exits while the launch controller
   remains alive. A separate native observer persists these three records. */
struct observation_request {
    uint32_t version, size, kind, reserved;
    uint64_t target, expected_pid, expected_generation, deadline_ns;
};
struct observation_snapshot {
    uint32_t version, size, kind, flags;
    uint64_t observed_at_ns, completed_at_ns, pid, parent_pid, image_generation, object_token, ticks;
    uint32_t state, threads, blocked_threads, pages, page_limit;
    uint32_t owned_channels, channel_limit, owned_names, name_limit, pipe_references, pipe_limit, reserved;
};
static uint64_t monotonic_ns(void) { return (uint64_t)trap(46, 0, 0, 0); }
static int observe_child(pid_t child, struct observation_snapshot *output) {
    const struct observation_request request = {1, sizeof(request), 1, 0,
        (uint64_t)child, (uint64_t)child, 1, monotonic_ns() + 2000000000ULL};
    CHECK(trap(90, (unsigned long)&request, (unsigned long)output, 0) == 0);
    CHECK(output->version == 1 && output->size == sizeof(*output) && output->pid == (uint64_t)child &&
          output->parent_pid == (uint64_t)getpid() && output->image_generation == 1);
    return 0;
}
static int owner_event(const struct owner_event *event) {
    return write(5, event, sizeof(*event)) == sizeof(*event);
}
static int terminal_owner_death(void) {
    CHECK(open("/tests/terminal_input", O_RDONLY) == 6);
    struct identity parent; CHECK(identify(&parent, 1) == 0);
    struct termios mode; CHECK(tcgetattr(0, &mode) == 0);
    mode.c_cc[VMIN] = 1; mode.c_cc[VTIME] = 0;
    CHECK(tcsetattr(0, TCSANOW, &mode) == 0);
    int entered[2]; CHECK(pipe(entered) == 0);
    const pid_t child = fork(); CHECK(child >= 0);
    if (!child) {
        CHECK(close(entered[0]) == 0);
        struct identity before; CHECK(identify(&before, 1) == 0 && before.owner == parent.owner &&
            before.service == parent.service && before.controller == parent.pid && before.owner != before.controller);
        struct owner_event event = {{0}};
        event.value[oe_kind] = 2; event.value[oe_pid] = before.pid;
        event.value[oe_parent] = parent.pid; event.value[oe_owner] = before.owner;
        event.value[oe_actor] = before.service; event.value[oe_started_ns] = monotonic_ns();
        event.value[oe_terminal_send] = before.terminal_send;
        event.value[oe_terminal_receive] = before.terminal_receive;
        event.value[oe_ready] = before.ready; event.value[oe_ack] = before.ack;
        event.value[oe_authority] = before.authority;
        CHECK(write(entered[1], "R", 1) == 1 && close(entered[1]) == 0);
        char byte = 0; errno = 0;
        const ssize_t read_result = read(0, &byte, 1); const int read_error = errno;
        event.value[oe_finished_ns] = monotonic_ns();
        event.value[oe_read_result] = (owner_u64)read_result; event.value[oe_read_errno] = (unsigned)read_error;
        CHECK(read_result == -1 && read_error == EPIPE &&
            event.value[oe_finished_ns] >= event.value[oe_started_ns] &&
            event.value[oe_finished_ns] - event.value[oe_started_ns] < 10000000000ULL);
        event.value[oe_raw_send] = (owner_u64)trap(4, before.terminal_send, (unsigned long)&byte, 1);
        event.value[oe_raw_receive] = (owner_u64)trap(5, before.terminal_receive, (unsigned long)&byte, 1);
        CHECK((long long)event.value[oe_raw_send] == -1 && (long long)event.value[oe_raw_receive] == -1);
        unsigned count = 0;
        for (unsigned ordinal = 0; ordinal < 32; ++ordinal) {
            struct channel_info info = {0};
            const long found = trap(81, 1, ordinal, (unsigned long)&info);
            if (found == -15) break;
            CHECK(found == 0 && info.peer_pid == parent.pid && info.controller_pid == parent.pid &&
                (info.handle == before.ready || info.handle == before.ack));
            ++count;
        }
        CHECK(count == 2); event.value[oe_controller_preserved] = 1;
        char *next[] = {(char *)self, "unexpected", NULL}; errno = 0;
        event.value[oe_exec_result] = (owner_u64)execve(self, next, environ);
        event.value[oe_exec_errno] = (unsigned)errno;
        CHECK((long long)event.value[oe_exec_result] == -1 && event.value[oe_exec_errno] == EIO &&
            (uint64_t)getpid() == before.pid && trap(87, (unsigned long)getpid(), 3, 0) == (long)before.authority);
        CHECK(read(6, &byte, 1) == 1 && byte == 'A'); event.value[oe_file_byte] = (unsigned char)byte;
        event.value[oe_pipe_result] = (owner_u64)read(4, &byte, 1);
        CHECK(event.value[oe_pipe_result] == 0 && owner_event(&event)); return 0;
    }
    CHECK(close(entered[1]) == 0);
    char byte = 0; CHECK(read(entered[0], &byte, 1) == 1 && byte == 'R' && close(entered[0]) == 0);
    struct observation_snapshot snapshot = {0};
    const uint64_t deadline = monotonic_ns() + 5000000000ULL;
    do {
        CHECK(observe_child(child, &snapshot) == 0 && monotonic_ns() < deadline);
        if (snapshot.state == 5 && snapshot.threads == 1 && snapshot.blocked_threads == 1) break;
        sched_yield();
    } while (1);
    struct owner_event event = {{0}};
    event.value[oe_kind] = 1; event.value[oe_pid] = (uint64_t)getpid();
    event.value[oe_owner] = parent.owner; event.value[oe_actor] = parent.service;
    event.value[oe_child] = (uint64_t)child; event.value[oe_started_ns] = snapshot.observed_at_ns;
    event.value[oe_finished_ns] = snapshot.completed_at_ns; event.value[oe_generation] = snapshot.image_generation;
    event.value[oe_threads] = snapshot.threads; event.value[oe_blocked] = snapshot.blocked_threads;
    event.value[oe_state] = snapshot.state;
    CHECK(owner_event(&event) && packet(5, (uint64_t)child));
    CHECK(wait_child(child) == 0 && read(6, &byte, 1) == 1 && byte == 'B');
    memset(&event, 0, sizeof(event)); event.value[oe_kind] = 3;
    event.value[oe_pid] = (uint64_t)getpid(); event.value[oe_child] = (uint64_t)child;
    event.value[oe_owner] = parent.owner; event.value[oe_actor] = parent.service;
    event.value[oe_file_byte] = (unsigned char)byte; event.value[oe_wait_status] = 0;
    CHECK(owner_event(&event)); return 0;
}
int main(int argc, char **argv) {
    self = argv[0]; CHECK(argc >= 2 && constructor_ready && tls_value == 37);
    if (!strcmp(argv[1], "after")) { CHECK(argc == 5); return after_exec(argv[2], argv[3], argv[4]); }
    if (!strcmp(argv[1], "actor-death")) return actor_death();
    if (!strcmp(argv[1], "owner-exit")) return owner_exit();
    if (!strcmp(argv[1], "owner-kill")) return owner_kill();
    if (!strcmp(argv[1], "terminal-owner-death")) return terminal_owner_death();
    CHECK(!strcmp(argv[1], "direct") || !strcmp(argv[1], "fork") || !strcmp(argv[1], "authority"));
    return positive(argv[1]);
}
