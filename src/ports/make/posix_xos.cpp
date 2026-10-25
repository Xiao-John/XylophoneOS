// SPDX-License-Identifier: Apache-2.0
#define _POSIX_C_SOURCE 200809L
// XOS process mechanisms for the pinned sbase Make always-build profile.
#include <xos/sdk.hpp>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
extern "C" {
#include "make.h"
extern char** environ;
}

namespace {
pid_t active_pid;
xos::i64 foreground(pid_t child, bool active) {
    xos::process_foreground group{1, sizeof(group), child > 0 ? 1u : 0u, 0, {}};
    if (child > 0) { group.pids[0] = static_cast<xos::u64>(child); }
    return xos::sdk::syscall(xos::sys_process_foreground,
        reinterpret_cast<xos::u64>(&group), active ? 1 : 0);
}
[[noreturn]] void fatal(const char* message, int code) {
    fprintf(stderr, "make: %s; partial outputs retained\n", message);
    exit(code);
}
}

extern "C" void killchild(void) {
    if (active_pid > 0) {
        const pid_t child = active_pid;
        active_pid = 0;
        const auto cancelled = xos::sdk::syscall(xos::sys_process_cancel,
                                                static_cast<xos::u64>(child));
        int status = 0;
        pid_t waited;
        do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
        if (cancelled < 0 && waited < 0) {
            fprintf(stderr, "make: child cleanup failed for PID %ld\n", static_cast<long>(child));
        }
    }
    (void)foreground(0, false);
}

extern "C" int is_dir(char* name) {
    struct stat value{};
    return stat(name, &value) == 0 && S_ISDIR(value.st_mode);
}

extern "C" void exportvar(char* name, char* value) {
    if (setenv(name, value, 1) != 0) {
        perror("make: export"); exit(1);
    }
}

extern "C" time_t stamp(char* name) {
    struct stat value{};
    if (stat(name, &value) == 0) { return 0; } // Existence only: never invent a modification time.
    if (errno == ENOENT || errno == ENOTDIR) { return -1; }
    fprintf(stderr, "make: stat %s: %s\n", name, strerror(errno));
    exit(1);
}

extern "C" int launch(char* command, int ignore) {
    const char* shell = getmacro(const_cast<char*>("SHELL"));
    if (strcmp(shell, "/usr/bin/dash") != 0) {
        fatal("this profile requires SHELL=/usr/bin/dash", 2);
    }
    const auto began = foreground(0, true);
    if (began < 0) {
        fatal(began == xos::process_error_state ? "recipe cancelled before launch" :
              "cannot register foreground recipe", began == xos::process_error_state ? 137 : 125);
    }
    if (fflush(nullptr) != 0) { fatal("cannot flush output before fork", 125); }
    const pid_t child = fork();
    if (child < 0) {
        perror("make: fork"); fatal("recipe fork failed", 125);
    }
    if (child == 0) {
        char* arguments[] = {const_cast<char*>("dash"),
            const_cast<char*>(ignore ? "-c" : "-ec"), command, nullptr};
        execve(shell, arguments, environ);
        const int error = errno;
        fprintf(stderr, "make: exec %s: %s\n", shell, strerror(error));
        _exit(error == ENOENT || error == ENOTDIR ? 127 : 126);
    }
    active_pid = child;
    const auto registered = foreground(child, true);
    if (registered < 0) {
        killchild();
        fatal(registered == xos::process_error_state ? "recipe cancelled during launch" :
              "cannot register recipe PID", registered == xos::process_error_state ? 137 : 125);
    }
    int status = 0;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited != child) { fatal("recipe wait failed", 125); }
    active_pid = 0;
    if (foreground(0, false) < 0) { fatal("cannot release foreground recipe", 125); }
    if ((WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL) ||
        (WIFEXITED(status) && WEXITSTATUS(status) == 137)) {
        // XOS wait reports forced cancellation/faults as SIGKILL; the
        // intervening recipe Shell can propagate that as exit 137. This
        // bounded Make profile reserves 137 even if a script returns it.
        // They stop Make even under -i, a '-' prefix, or .IGNORE.
        fatal("recipe terminated (SIGKILL/Escape or fault)", 137);
    }
    if (WIFEXITED(status)) { return WEXITSTATUS(status); }
    if (WIFSIGNALED(status)) { return 128 + WTERMSIG(status); }
    fatal("unsupported recipe wait outcome", 125);
}
