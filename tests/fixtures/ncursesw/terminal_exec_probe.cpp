// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/spawn.hpp>
#include <xos/thread_abi.hpp>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>
#include <sys/wait.h>

namespace {
struct marker { xos::u64 magic; xos::u32 version, size; };
[[gnu::section(".xos.tty"), gnu::used]] const marker terminal_marker{
    xos::terminal_image_abi_magic, 1, sizeof(marker)};
bool message(const char* label) {
    char line[80];
    const int length = snprintf(line, sizeof(line), "%s pid=%llu\n", label,
                                static_cast<unsigned long long>(xos::sdk::pid()));
    if (length <= 0 || static_cast<unsigned>(length) >= sizeof(line)) return false;
    int sent = 0;
    while (sent < length) {
        const auto result = write(1, line + sent, static_cast<size_t>(length - sent));
        if (result <= 0) return false;
        sent += static_cast<int>(result);
    }
    return true;
}
bool resources(xos::thread_stats& stats) {
    return xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&stats)) == 0;
}
bool same_resources(const xos::thread_stats& a, const xos::thread_stats& b) {
    return a.processes == b.processes && a.threads == b.threads && a.reserved == b.reserved &&
           a.results == b.results && a.free_pages == b.free_pages &&
           a.process_user_pages == b.process_user_pages && a.process_kernel_stack_pages == b.process_kernel_stack_pages;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc > 1 && xos::sdk::equal(args[1], "fork-exec")) {
        if (dup(1) != 3 || dup(1) != 4 || fcntl(3, F_SETFD, FD_CLOEXEC) != 0) return 58;
        struct termios tty{};
        if (tcgetattr(0, &tty) != 0) return 59;
        tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 1;
        if (tcsetattr(0, TCSANOW, &tty) != 0) return 60;
        const pid_t child = fork();
        if (child == 0) {
            char missing[] = "/missing", *missing_args[] = {missing, nullptr};
            errno = 0;
            if (execv(missing, missing_args) != -1 || errno != ENOENT || !isatty(4) ||
                !message("TTY_FORK_EXEC_BEFORE")) _exit(61);
            char target[] = "/bin/ttyexec.elf", after[] = "after", *next[] = {target, after, nullptr};
            (void)execv(target, next);
            _exit(62);
        }
        int status = 0;
        if (child < 0 || waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ||
            fcntl(3, F_GETFD) != FD_CLOEXEC || !isatty(4) || tcgetattr(0, &tty) != 0 || tty.c_cc[VTIME] != 1)
            return 63;
        return message("TTY_FORK_EXEC_PARENT") ? 0 : 64;
    }
    if (startup->argc > 1 && xos::sdk::equal(args[1], "malformed-child")) {
        int release[2]{};
        if (pipe(release) != 0) return 54;
        const pid_t sibling = fork();
        if (sibling == 0) {
            char signal = 0;
            struct termios mode{};
            const char marker[] = "TTY_HEALTHY_SIBLING\n";
            if (read(release[0], &signal, 1) != 1 || signal != 's' ||
                tcgetattr(0, &mode) != 0 || write(1, marker, sizeof(marker) - 1) != sizeof(marker) - 1)
                _exit(55);
            _exit(0);
        }
        if (sibling < 0) return 56;
        const pid_t child = fork();
        if (child == 0) {
            xos::channel_info first{}, second{};
            if (xos::sdk::channel_get(0, first) != 0 || xos::sdk::channel_get(1, second) != 0 ||
                first.rights == second.rights || first.peer_pid != second.peer_pid) _exit(48);
            const xos::u32 send = first.rights == xos::channel_send ? first.handle : second.handle;
            const xos::u32 receive = first.rights == xos::channel_receive ? first.handle : second.handle;
            const char malformed = 'x';
            if (xos::sdk::ipc_send(send, &malformed, 1) != 0) _exit(49);
            const xos::i64 now = xos::sdk::syscall(xos::sys_clock_monotonic);
            if (now < 0) _exit(50);
            const xos::i64 closed = xos::sdk::channel_wait(receive, static_cast<xos::u64>(now) + 3000000000ull);
            if (closed >= 0 || closed == xos::thread_error_timeout) _exit(51);
            _exit(0);
        }
        int status = 0;
        struct termios mode{};
        if (child < 0 || waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ||
            !isatty(0) || tcgetattr(0, &mode) != 0) return 52;
        const char signal = 's';
        if (write(release[1], &signal, 1) != 1 || waitpid(sibling, &status, 0) != sibling ||
            !WIFEXITED(status) || WEXITSTATUS(status) != 0 || tcgetattr(0, &mode) != 0) return 57;
        return message("TTY_BAD_CHILD_ISOLATED") ? 0 : 53;
    }
    const bool interrupt_write = startup->argc > 1 && xos::sdk::equal(args[1], "interrupt");
    const bool interrupt_close = startup->argc > 1 && xos::sdk::equal(args[1], "interrupt-close");
    if (interrupt_write || interrupt_close) {
        int ready[2]{};
        if (pipe(ready) != 0) return 39;
        const pid_t child = fork();
        if (child == 0) {
            const char signal = 'r';
            if (write(ready[1], &signal, 1) != 1) _exit(40);
            const xos::i64 now = xos::sdk::syscall(xos::sys_clock_monotonic);
            if (now < 0 || xos::sdk::syscall(xos::sys_sleep_until,
                    static_cast<xos::u64>(now) + 200000000ull) != 0) _exit(41);
            if (interrupt_close) _exit(0);
            const char text[] = "TTY_CHILD_INTERRUPT\n";
            if (write(1, text, sizeof(text) - 1) != sizeof(text) - 1) _exit(42);
            _exit(0);
        }
        if (child < 0) return 43;
        char signal = 0;
        if (read(ready[0], &signal, 1) != 1 || signal != 'r') return 44;
        errno = 0;
        char input = 0;
        if (read(0, &input, 1) != -1 || errno != EINTR) return 45;
        int status = 0;
        if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ||
            !isatty(0)) return 46;
        return message(interrupt_close ? "TTY_PARENT_CLOSE_INTERRUPTED" : "TTY_PARENT_INTERRUPTED") ? 0 : 47;
    }
    if (startup->argc > 1 && xos::sdk::equal(args[1], "capacity")) {
        int ready[2]{}, release[2]{};
        if (pipe(ready) != 0 || pipe(release) != 0) return 21;
        pid_t children[2]{};
        for (unsigned i = 0; i < 2; ++i) {
            children[i] = fork();
            if (children[i] == 0) {
                char byte = 'r';
                if (write(ready[1], &byte, 1) != 1 || read(release[0], &byte, 1) != 1) _exit(22);
                _exit(0);
            }
            if (children[i] < 0) return 23;
        }
        for (unsigned i = 0; i < 2; ++i) {
            char byte = 0;
            if (read(ready[0], &byte, 1) != 1 || byte != 'r') return 24;
        }
        // Verify the specific failure point, rather than attributing any
        // earlier process or memory exhaustion to the channel quota.
        xos::channel_info first{}, second{};
        if (xos::sdk::channel_get(0, first) != 0 || xos::sdk::channel_get(1, second) != 0 ||
            first.rights == second.rights || first.peer_pid != second.peer_pid) return 33;
        xos::thread_stats before{}, after{};
        if (!resources(before)) return 36;
        const xos::i64 staged = xos::sdk::syscall(xos::sys_process_fork_prepare);
        if (staged <= 0) return 34;
        xos::channel_fork_pair pair{xos::channel_version, sizeof(xos::channel_fork_pair),
            static_cast<xos::u64>(staged), first.rights == xos::channel_send ? first.handle : second.handle,
            first.rights == xos::channel_receive ? first.handle : second.handle, 0, 0};
        if (xos::sdk::channel_fork(pair) != xos::process_error_resources || pair.child_send != 0 ||
            pair.child_receive != 0 || xos::sdk::syscall(xos::sys_process_abort, static_cast<xos::u64>(staged)) != 0)
            return 35;
        if (!resources(after) || !same_resources(before, after)) return 37;
        errno = 0;
        const pid_t excess = fork();
        if (excess == 0) _exit(0);
        if (excess > 0) { int ignored = 0; (void)waitpid(excess, &ignored, 0); return 25; }
        if (errno != ENOMEM || !isatty(0)) return 26;
        if (!resources(after) || !same_resources(before, after)) return 38;
        struct termios mode{};
        if (tcgetattr(0, &mode) != 0) return 27;
        const char release_bytes[] = {'x', 'x'};
        if (write(release[1], release_bytes, sizeof(release_bytes)) != sizeof(release_bytes)) return 28;
        for (const auto child : children) {
            int status = 0;
            if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) return 29;
        }
        const pid_t recovered = fork();
        if (recovered == 0) _exit(isatty(1) ? 0 : 30);
        int status = 0;
        if (recovered < 0 || waitpid(recovered, &status, 0) != recovered ||
            !WIFEXITED(status) || WEXITSTATUS(status) != 0) return 31;
        return message("TTY_FORK_CAP_OK") ? 0 : 32;
    }
    if (startup->argc > 1 && xos::sdk::equal(args[1], "fork")) {
        const int duplicate = dup(1);
        if (duplicate < 0) return 15;
        struct termios tty{};
        if (tcgetattr(0, &tty) != 0) return 16;
        tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 1;
        if (tcsetattr(0, TCSANOW, &tty) != 0) return 17;
        const pid_t child = fork();
        if (child == 0) {
            struct termios child_mode{};
            const char text[] = "TTY_FORK_CHILD\n";
            if (!isatty(duplicate) || tcgetattr(0, &child_mode) != 0 || child_mode.c_cc[VTIME] != 1 ||
                write(duplicate, text, sizeof(text) - 1) != sizeof(text) - 1) _exit(18);
            _exit(0);
        }
        int status = 0;
        if (child < 0 || waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0 ||
            !isatty(duplicate) || tcgetattr(0, &tty) != 0 || tty.c_cc[VTIME] != 1) return 19;
        return message("TTY_FORK_PARENT") ? 0 : 20;
    }
    if (startup->argc > 1 && xos::sdk::equal(args[1], "drop-after")) {
        for (int fd = 0; fd < 3; ++fd) {
            errno = 0;
            if (fcntl(fd, F_GETFD) != -1 || errno != EBADF) return 10;
        }
        return 0;
    }
    if (startup->argc > 1 && xos::sdk::equal(args[1], "drop")) {
        if (!message("TTY_EXEC_DROP_READY")) return 11;
        for (int fd = 0; fd < 3; ++fd) if (fcntl(fd, F_SETFD, FD_CLOEXEC) != 0) return 12;
        char target[] = "/bin/ttyexec.elf", next[] = "drop-after", *next_args[] = {target, next, nullptr};
        (void)execv(target, next_args);
        return 13;
    }
    if (startup->argc > 1 && xos::sdk::equal(args[1], "after")) {
        errno = 0;
        if (fcntl(3, F_GETFD) != -1 || errno != EBADF || !isatty(4) || !isatty(0) || !isatty(1)) return 1;
        struct termios tty{};
        if (tcgetattr(0, &tty) != 0 || tty.c_cc[VMIN] != 0 || tty.c_cc[VTIME] != 1) return 2;
        return message("TTY_EXEC_AFTER") ? 0 : 3;
    }
    if (dup(1) != 3 || dup(1) != 4 || fcntl(3, F_SETFD, FD_CLOEXEC) != 0) return 4;
    struct termios tty{};
    if (tcgetattr(0, &tty) != 0) return 5;
    tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 1;
    if (tcsetattr(0, TCSANOW, &tty) != 0) return 6;
    char missing[] = "/missing", *missing_args[] = {missing, nullptr};
    errno = 0;
    if (execv(missing, missing_args) != -1 || errno != ENOENT || !isatty(4)) return 7;
    char legacy[] = "/bin/legacy.elf", *legacy_args[] = {legacy, nullptr};
    errno = 0;
    if (execv(legacy, legacy_args) != -1 || errno != ENOTSUP || !isatty(4)) return 14;
    if (!message("TTY_EXEC_BEFORE")) return 8;
    char target[] = "/bin/ttyexec.elf", after[] = "after", *args2[] = {target, after, nullptr};
    (void)execv(target, args2);
    return 9;
}
