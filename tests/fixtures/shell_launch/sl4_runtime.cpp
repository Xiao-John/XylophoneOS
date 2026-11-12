// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;
namespace {
constexpr const char* executable = "/bin/sl4_probe";
constexpr const char* renamed = "/bin/renamed_probe";
bool require(bool value, const char* message) {
    if (!value) { fprintf(stderr, "SL4_FAIL %s errno=%d\n", message, errno); }
    return value;
}
bool cwd_is(const char* expected) {
    char path[256];
    return getcwd(path, sizeof(path)) != nullptr && strcmp(path, expected) == 0;
}
xos::i64 authority() {
    return xos::sdk::syscall(xos::sys_process_authority, xos::sdk::pid(),
                            static_cast<xos::u64>(xos::process_authority_mode::query));
}
int child_status(pid_t child) {
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status)) return 125;
    return WEXITSTATUS(status);
}
int spawn(const char* path, char* const args[], const posix_spawn_file_actions_t* actions = nullptr) {
    pid_t child = -1;
    const int error = posix_spawn(&child, path, actions, nullptr, args, nullptr);
    if (error != 0) { errno = error; return 125; }
    return child_status(child);
}
bool content(const char* path, const char* expected) {
    const int fd = open(path, O_RDONLY);
    if (fd < 0) return false;
    char data[128];
    const ssize_t count = read(fd, data, sizeof(data));
    const int closed = close(fd);
    return closed == 0 && count == static_cast<ssize_t>(strlen(expected)) &&
           memcmp(data, expected, static_cast<size_t>(count)) == 0;
}
int chain(int depth) {
    if (!require(authority() == 1, "spawn chain authority")) return 1;
    if (depth == 0) { puts("SL4_CHAIN_LEAF_OK"); return 0; }
    char remaining[12];
    snprintf(remaining, sizeof(remaining), "%d", depth - 1);
    char* args[] = {const_cast<char*>(executable), const_cast<char*>("chain"), remaining, nullptr};
    if (!require(spawn(executable, args) == 0, "spawn chain child")) return 2;
    if (depth == 4) puts("SL4_CHAIN_FOUR_OK");
    return 0;
}
int denied(bool after_exec) {
    if (!require(authority() == 0, "reduced authority stays zero")) return 1;
    const auto raw = xos::sdk::syscall(xos::sys_process_create, 0,
        reinterpret_cast<xos::u64>("denied"), 6);
    if (!require(raw == xos::process_error_denied, "raw create denied")) return 2;
    pid_t child = -1;
    char* args[] = {const_cast<char*>(executable), const_cast<char*>("query"), nullptr};
    if (!require(posix_spawn(&child, executable, nullptr, nullptr, args, nullptr) == EPERM && child == -1,
                 "POSIX spawn denied without changing output PID")) return 3;
    errno = 0;
    if (!require(fork() < 0 && errno == EPERM, "fork denied")) return 4;
    const auto escalation = xos::sdk::syscall(xos::sys_process_authority, xos::sdk::pid(),
        static_cast<xos::u64>(xos::process_authority_mode::set));
    if (!require(escalation < 0 && authority() == 0, "running child cannot grant itself authority")) return 5;
    if (after_exec) { puts("SL4_DENIED_EXEC_OK"); return 0; }
    char* next[] = {const_cast<char*>(renamed), const_cast<char*>("denied_after"), nullptr};
    execve(renamed, next, environ);
    require(false, "exec renamed image after reduction");
    return 6;
}
xos::i64 clear_child(xos::u64 child, void*) {
    return xos::sdk::syscall(xos::sys_process_authority, child,
        static_cast<xos::u64>(xos::process_authority_mode::clear));
}
int reduction() {
    if (!require(authority() == 1, "ordinary caller can create")) return 1;
    xos::sdk::spawn_options options{};
    options.prepare_child = clear_child;
    const char* args[] = {executable, "denied"};
    const auto child = xos::sdk::spawn_file_options(executable, 2, args, options);
    xos::process_status status{};
    if (!require(child > 0 && xos::sdk::wait(static_cast<xos::u64>(child), status) == 0 &&
                 status.outcome == xos::process_outcome::exited && status.code == 0,
                 "reduced child finishes without gaining rights")) return 2;
    puts("SL4_REDUCTION_OK");
    return 0;
}
int inherited_child() {
    char byte = 0;
    const char* value = getenv("SL4_VALUE");
    if (!require(value && strcmp(value, "alpha beta") == 0 && cwd_is("/tests/work") && authority() == 1,
                 "spawn environment/cwd/authority") ||
        !require(read(0, &byte, 1) == 1 && byte == 'b', "spawn stdin shares offset")) return 1;
    return write(1, "child\n", 6) == 6 ? 0 : 2;
}
int inherited_exec(int fd, int alias, int closed, pid_t previous_pid) {
    char first = 0, second = 0;
    errno = 0;
    if (!require(getpid() == previous_pid && cwd_is("/tests/work"), "exec PID and cwd") ||
        !require(fcntl(closed, F_GETFD) < 0 && errno == EBADF, "exec CLOEXEC") ||
        !require(read(fd, &first, 1) == 1 && first == 'b' && read(alias, &second, 1) == 1 && second == 'c',
                 "exec inherited aliases share description") ||
        !require(authority() == 1, "exec preserves authority")) return 1;
    puts("SL4_EXEC_FDS_OK");
    return 0;
}
int inheritance() {
    if (!require(chdir("/tests/work") == 0 && setenv("SL4_VALUE", "alpha beta", 1) == 0,
                 "inheritance setup")) return 1;
    const int original_stdin = dup(0);
    const int input = open("input", O_CREAT | O_TRUNC | O_RDWR, 0666);
    if (!require(original_stdin >= 0 && input >= 0 && write(input, "abcdef", 6) == 6 &&
                 lseek(input, 0, SEEK_SET) == 0 && dup2(input, 0) == 0, "shared stdin setup")) return 2;
    char byte = 0;
    if (!require(read(0, &byte, 1) == 1 && byte == 'a', "parent stdin first byte")) return 3;
    posix_spawn_file_actions_t actions;
    if (!require(posix_spawn_file_actions_init(&actions) == 0 &&
                 posix_spawn_file_actions_addopen(&actions, 1, "spawn.out", O_CREAT | O_TRUNC | O_WRONLY, 0666) == 0,
                 "relative stdout file action")) return 4;
    char* args[] = {const_cast<char*>(executable), const_cast<char*>("inherited_child"), nullptr};
    const int result = spawn(executable, args, &actions);
    posix_spawn_file_actions_destroy(&actions);
    if (!require(result == 0 && read(0, &byte, 1) == 1 && byte == 'c' && content("spawn.out", "child\n"),
                 "spawn returns shared offset and redirected content")) return 5;
    if (!require(dup2(original_stdin, 0) == 0 && close(original_stdin) == 0 && close(input) == 0,
                 "restore original stdin")) return 6;

    const int kept = open("input", O_RDONLY);
    const int alias = dup(kept);
    const int drop = open("input", O_RDONLY | O_CLOEXEC);
    if (!require(kept >= 0 && alias >= 0 && drop >= 0 && read(kept, &byte, 1) == 1 && byte == 'a',
                 "fork/exec fd setup")) return 7;
    if (fflush(nullptr) != 0) return 8;
    const pid_t child = fork();
    if (child == 0) {
        char a[12], b[12], c[12], pid[24];
        snprintf(a, sizeof(a), "%d", kept); snprintf(b, sizeof(b), "%d", alias);
        snprintf(c, sizeof(c), "%d", drop); snprintf(pid, sizeof(pid), "%ld", static_cast<long>(getpid()));
        char* next[] = {const_cast<char*>(executable), const_cast<char*>("inherited_exec"), a, b, c, pid, nullptr};
        execve(executable, next, environ);
        _exit(99);
    }
    if (!require(child > 0 && child_status(child) == 0 && lseek(kept, 0, SEEK_CUR) == 3 &&
                 (fcntl(drop, F_GETFD) & FD_CLOEXEC) != 0, "fork/exec shares offsets and only closes child CLOEXEC")) return 9;
    if (!require(close(kept) == 0 && close(alias) == 0 && close(drop) == 0 && chdir("/") == 0,
                 "inheritance cleanup")) return 10;
    puts("SL4_INHERITANCE_OK");
    return 0;
}
int copy_stream() {
    char bytes[64];
    for (;;) {
        const ssize_t count = read(0, bytes, sizeof(bytes));
        if (count < 0) return 1;
        if (count == 0) return 0;
        ssize_t done = 0;
        while (done < count) {
            const ssize_t written = write(1, bytes + done, static_cast<size_t>(count - done));
            if (written <= 0) return 2;
            done += written;
        }
    }
}
}
int main(int argc, char** argv) {
    if (argc < 2) return 2;
    if (strcmp(argv[1], "query") == 0) {
        if (!require(authority() == 1, "ordinary application authority")) return 1;
        puts("SL4_QUERY_OK"); return 0;
    }
    if (strcmp(argv[1], "chain") == 0 && argc == 3) return chain(atoi(argv[2]));
    if (strcmp(argv[1], "reduce") == 0) return reduction();
    if (strcmp(argv[1], "denied") == 0) return denied(false);
    if (strcmp(argv[1], "denied_after") == 0) return denied(true);
    if (strcmp(argv[1], "inherit") == 0) return inheritance();
    if (strcmp(argv[1], "inherited_child") == 0) return inherited_child();
    if (strcmp(argv[1], "inherited_exec") == 0 && argc == 6)
        return inherited_exec(atoi(argv[2]), atoi(argv[3]), atoi(argv[4]), static_cast<pid_t>(atol(argv[5])));
    if (strcmp(argv[1], "copy") == 0) return copy_stream();
    if (strcmp(argv[1], "compare") == 0 && argc == 4) {
        if (!require(content(argv[2], argv[3]), "redirected pipeline bytes")) return 1;
        puts("SL4_PIPE_BYTES_OK"); return 0;
    }
    if (strcmp(argv[1], "environment") == 0) {
        const char* value = getenv("SL4_VALUE");
        if (!require(value && strcmp(value, "alpha beta") == 0 && cwd_is("/tests/work"), "nested shell context")) return 1;
        puts("SL4_SHELL_CONTEXT_OK"); return 0;
    }
    if (strcmp(argv[1], "arguments") == 0 && argc == 4 && argv[2][0] == 0 && strcmp(argv[3], "two words") == 0) {
        puts("SL4_ARGUMENTS_OK"); return 0;
    }
    if (strcmp(argv[1], "same_pid") == 0 && argc == 3 && getpid() == static_cast<pid_t>(atol(argv[2]))) {
        puts("SL4_DASH_EXEC_PID_OK"); return 0;
    }
    return 2;
}
