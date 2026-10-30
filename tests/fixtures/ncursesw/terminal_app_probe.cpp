// SPDX-License-Identifier: Apache-2.0
#include <xos/spawn.hpp>
#include <errno.h>
#include <termios.h>
#include <unistd.h>

namespace {
struct marker { xos::u64 magic; xos::u32 version, size; };
[[gnu::section(".xos.tty"), gnu::used]] const marker terminal_marker{
    xos::terminal_image_abi_magic, 1, sizeof(marker)};
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (startup == nullptr || !isatty(0) || !isatty(1) || !isatty(2)) return 1;
    struct termios tty{};
    if (tcgetattr(0, &tty) != 0 || tty.c_cc[VMIN] != 1 || tty.c_cc[VTIME] != 0) return 9;
    tty.c_lflag |= ECHO; errno = 0;
    if (tcsetattr(0, TCSANOW, &tty) != -1 || errno != ENOTSUP) return 10;
    if (tcgetattr(0, &tty) != 0 || tty.c_lflag != 0) return 11;
    if (tcsetattr(0, TCSADRAIN, &tty) != 0 || tcdrain(1) != 0) return 15;
    errno = 0;
    if (tcflush(0, TCIFLUSH) != -1 || errno != ENOTSUP) return 16;
    tty.c_cc[VMIN] = 0;
    if (tcsetattr(0, TCSANOW, &tty) != 0) return 12;
    char empty = 0;
    if (read(0, &empty, 1) != 0) return 13;
    tty.c_cc[VMIN] = 1;
    if (tcsetattr(0, TCSANOW, &tty) != 0) return 14;
    const int duplicate = dup(1);
    if (duplicate < 0 || close(1) != 0) return 2;
    errno = 0;
    if (fork() != -1 || errno != ENOTSUP) return 5;
    char executable[] = "/missing", *arguments[] = {executable, nullptr};
    errno = 0;
    if (execv(executable, arguments) != -1 || errno != ENOTSUP) return 6;
    const char ready[] = "W1_APP_READY\n";
    for (u32 i = 0; i < sizeof(ready) - 1; ++i)
        if (write(duplicate, ready + i, 1) != 1) return 7;
    char input = 0;
    if (read(0, &input, 1) != 1 || input != 'A') return 8;
    const char message[] = "W1_APP_OK\n";
    for (u32 i = 0; i < sizeof(message) - 1; ++i)
        if (write(duplicate, message + i, 1) != 1) return 3;
    if (tcdrain(duplicate) != 0) return 17;
    if (close(duplicate) != 0) return 4;
    return 0;
}
