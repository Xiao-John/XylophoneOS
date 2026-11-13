/* SPDX-License-Identifier: Apache-2.0 */
/* POSIX process conveniences that the kernel does not provide directly. */
#define _POSIX_C_SOURCE 200809L
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
constexpr unsigned max_popen = 32;
struct popen_entry {
    FILE* stream;
    pid_t pid;
    bool reserved;
};
popen_entry popen_table[max_popen];
// Short critical sections only (table scan/commit); no blocking work inside.
volatile int popen_lock;
void lock_table() { while (__atomic_exchange_n(&popen_lock, 1, __ATOMIC_ACQUIRE) != 0) {} }
void unlock_table() { __atomic_store_n(&popen_lock, 0, __ATOMIC_RELEASE); }

const char* shell_path() {
    const char* configured = getenv("XOS_SHELL");
    if (configured != nullptr && configured[0] != '\0' && access(configured, X_OK) == 0) {
        return configured;
    }
    if (access("/bin/sh", X_OK) == 0) { return "/bin/sh"; }
    if (access("/usr/bin/dash", X_OK) == 0) { return "/usr/bin/dash"; }
    return nullptr;
}

int spawn_shell(const char* shell, const char* command, const posix_spawn_file_actions_t* actions) {
    char* const argv[] = {const_cast<char*>(shell), const_cast<char*>("-c"),
                          const_cast<char*>(command), nullptr};
    pid_t pid = 0;
    const int status = posix_spawn(&pid, shell, actions, nullptr, argv, environ);
    if (status != 0) { errno = status; return -1; }
    return static_cast<int>(pid);
}

int wait_for(pid_t pid) {
    int status = 0;
    for (;;) {
        const pid_t waited = waitpid(pid, &status, 0);
        if (waited == pid) { return status; }
        if (waited < 0 && errno == EINTR) { continue; }
        return -1;
    }
}
}  // namespace

extern "C" int system(const char* command) {
    if (command == nullptr) { return shell_path() != nullptr ? 1 : 0; }
    const char* shell = shell_path();
    if (shell == nullptr) { errno = ENOENT; return 127 << 8; }
    (void)fflush(nullptr);
    const int pid = spawn_shell(shell, command, nullptr);
    if (pid < 0) {
        // POSIX: a shell that cannot be executed yields 127; other spawn
        // failures are reported as -1 with errno preserved.
        const int failure = errno;
        errno = failure;
        return failure == ENOENT ? (127 << 8) : -1;
    }
    return wait_for(pid);
}

extern "C" FILE* popen(const char* command, const char* mode) {
    if (command == nullptr || mode == nullptr || (mode[0] != 'r' && mode[0] != 'w')) {
        errno = EINVAL;
        return nullptr;
    }
    const char* shell = shell_path();
    if (shell == nullptr) { errno = ENOENT; return nullptr; }

    unsigned slot = max_popen;
    lock_table();
    for (unsigned i = 0; i < max_popen; ++i) {
        if (popen_table[i].stream == nullptr && !popen_table[i].reserved) {
            popen_table[i] = popen_entry{nullptr, 0, true};
            slot = i;
            break;
        }
    }
    unlock_table();
    if (slot == max_popen) { errno = EMFILE; return nullptr; }

    auto release_slot = [&]() {
        lock_table();
        popen_table[slot] = popen_entry{nullptr, 0, false};
        unlock_table();
    };

    int fds[2] = {-1, -1};
    if (pipe(fds) != 0) { release_slot(); return nullptr; }
    const int child_fd = mode[0] == 'r' ? fds[1] : fds[0];
    const int parent_fd = mode[0] == 'r' ? fds[0] : fds[1];
    const int target_fd = mode[0] == 'r' ? STDOUT_FILENO : STDIN_FILENO;

    // Keep this stream out of later spawned children.
    if (fcntl(parent_fd, F_SETFD, FD_CLOEXEC) < 0) {
        const int failure = errno;
        (void)close(fds[0]); (void)close(fds[1]);
        release_slot();
        errno = failure;
        return nullptr;
    }

    // Create the stream first: a failure here must not leave a child running.
    FILE* stream = fdopen(parent_fd, mode);
    if (stream == nullptr) {
        (void)close(fds[0]); (void)close(fds[1]);
        release_slot();
        return nullptr;
    }

    posix_spawn_file_actions_t actions;
    if (posix_spawn_file_actions_init(&actions) != 0) {
        (void)fclose(stream);
        (void)close(child_fd);
        release_slot();
        errno = ENOMEM;
        return nullptr;
    }
    int action_error = posix_spawn_file_actions_adddup2(&actions, child_fd, target_fd);
    // Never close the descriptor that was just mapped onto the target.
    if (action_error == 0 && child_fd != target_fd) {
        action_error = posix_spawn_file_actions_addclose(&actions, child_fd);
    }
    if (action_error == 0 && parent_fd != target_fd && parent_fd != child_fd) {
        action_error = posix_spawn_file_actions_addclose(&actions, parent_fd);
    }
    if (action_error != 0) {
        posix_spawn_file_actions_destroy(&actions);
        (void)fclose(stream);
        (void)close(child_fd);
        release_slot();
        errno = action_error;
        return nullptr;
    }
    (void)fflush(nullptr);
    const int pid = spawn_shell(shell, command, &actions);
    posix_spawn_file_actions_destroy(&actions);
    (void)close(child_fd);
    if (pid < 0) {
        (void)fclose(stream);
        release_slot();
        return nullptr;
    }

    lock_table();
    popen_table[slot] = popen_entry{stream, static_cast<pid_t>(pid), false};
    unlock_table();
    return stream;
}

extern "C" int pclose(FILE* stream) {
    if (stream == nullptr) { errno = EINVAL; return -1; }
    unsigned slot = max_popen;
    pid_t pid = 0;
    lock_table();
    for (unsigned i = 0; i < max_popen; ++i) {
        if (popen_table[i].stream == stream) {
            slot = i;
            pid = popen_table[i].pid;
            popen_table[i] = popen_entry{nullptr, 0, false};
            break;
        }
    }
    unlock_table();
    if (slot == max_popen) { errno = ECHILD; return -1; }
    (void)fclose(stream);
    return wait_for(pid);
}
