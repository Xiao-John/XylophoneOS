// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/spawn.hpp>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>

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
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
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
