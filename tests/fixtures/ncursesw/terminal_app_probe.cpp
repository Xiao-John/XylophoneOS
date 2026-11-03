// SPDX-License-Identifier: Apache-2.0
#include <xos/spawn.hpp>
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include <xos/terminal_client.hpp>
#include <xos/thread_abi.hpp>
#include <errno.h>
#include <termios.h>
#include <unistd.h>
#include <sys/select.h>
#include <sys/wait.h>

namespace {
struct marker { xos::u64 magic; xos::u32 version, size; };
[[gnu::section(".xos.tty"), gnu::used]] const marker terminal_marker{
    xos::terminal_image_abi_magic, 1, sizeof(marker)};
bool announce(int fd, const char* message) {
    for (xos::u32 i = 0; message[i] != '\0'; ++i)
        if (write(fd, message + i, 1) != 1) return false;
    return true;
}
int terminal_ready(long seconds) {
    fd_set readable{};
    FD_ZERO(&readable); FD_SET(0, &readable);
    timeval timeout{seconds, 0};
    const int count = select(1, &readable, nullptr, nullptr, &timeout);
    if (count == 0 && !FD_ISSET(0, &readable)) return 0;
    return count == 1 && FD_ISSET(0, &readable) ? 1 : -1;
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (startup == nullptr || !isatty(0) || !isatty(1) || !isatty(2)) return 1;
    terminal::client parent{};
    if (terminal::connect_startup(parent, startup) != 0) return 19;
    const i64 child_pid = sdk::syscall(sys_process_fork_prepare);
    if (child_pid == 0) {
        terminal::client child{};
        if (terminal::connect(child, parent.controller_pid, parent.service_pid) != 0) return 20;
        const char text[] = "W1_FORK_CHILD\n";
        u32 offset = 0;
        while (offset < sizeof(text) - 1) {
            const i64 written = terminal::write_until(child, text + offset,
                static_cast<u32>(sizeof(text) - 1 - offset), thread_deadline_infinite);
            if (written <= 0) return 21;
            offset += static_cast<u32>(written);
        }
        return 0;
    }
    if (child_pid < 0) return 22;
    channel_fork_pair pair{channel_version, sizeof(channel_fork_pair), static_cast<u64>(child_pid),
                           parent.send_handle, parent.receive_handle, 0, 0};
    if (sdk::channel_fork(pair) != 0 || terminal::register_fork(parent, pair) != 0) {
        (void)sdk::syscall(sys_process_abort, static_cast<u64>(child_pid)); return 23;
    }
    file::Client files{};
    if (!files.init()) { (void)sdk::syscall(sys_process_abort, static_cast<u64>(child_pid)); return 24; }
    i64 cloned = static_cast<i64>(file::status::would_block);
    for (u32 attempt = 0; attempt < 128 && cloned == static_cast<i64>(file::status::would_block); ++attempt) {
        cloned = files.clone_session(static_cast<u64>(child_pid));
        if (cloned == static_cast<i64>(file::status::would_block)) sdk::yield();
    }
    if (cloned != 0 || sdk::syscall(sys_process_fork_commit, static_cast<u64>(child_pid)) != 0) {
        (void)sdk::syscall(sys_process_abort, static_cast<u64>(child_pid)); return 25;
    }
    process_status child_status{};
    if (sdk::wait(static_cast<u64>(child_pid), child_status) != 0 ||
        child_status.outcome != process_outcome::exited || child_status.code != 0) return 26;
    struct termios tty{};
    if (tcgetattr(0, &tty) != 0 || tty.c_cc[VMIN] != 1 || tty.c_cc[VTIME] != 0) return 9;
    tty.c_lflag |= ECHO; errno = 0;
    if (tcsetattr(0, TCSANOW, &tty) != -1 || errno != ENOTSUP) return 10;
    if (tcgetattr(0, &tty) != 0 || tty.c_lflag != 0) return 11;
    if (tcsetattr(0, TCSADRAIN, &tty) != 0 || tcdrain(1) != 0) return 15;
    if (tcflush(0, TCIFLUSH) != 0 || tcsetattr(0, TCSAFLUSH, &tty) != 0) return 16;
    errno = 0;
    if (tcflush(0, TCOFLUSH) != -1 || errno != ENOTSUP) return 18;
    tty.c_cc[VMIN] = 0;
    if (tcsetattr(0, TCSANOW, &tty) != 0) return 12;
    char empty = 0;
    if (read(0, &empty, 1) != 0) return 13;
    tty.c_cc[VMIN] = 1;
    if (tcsetattr(0, TCSANOW, &tty) != 0) return 14;
    fd_set selected{};
    struct timeval instant{0, 0};
    FD_ZERO(&selected); FD_SET(0, &selected);
    if (select(1, &selected, nullptr, nullptr, &instant) != 0 || FD_ISSET(0, &selected)) return 28;
    FD_ZERO(&selected); FD_SET(0, &selected);
    struct timeval invalid_time{0, 1000000};
    errno = 0;
    if (select(1, &selected, nullptr, nullptr, &invalid_time) != -1 || errno != EINVAL) return 29;
    FD_ZERO(&selected); FD_SET(0, &selected); FD_SET(1, &selected);
    errno = 0;
    if (select(2, &selected, nullptr, nullptr, &instant) != -1 || errno != ENOTSUP) return 30;
    FD_ZERO(&selected); FD_SET(1, &selected);
    errno = 0;
    if (select(2, nullptr, &selected, nullptr, &instant) != -1 || errno != ENOTSUP) return 31;
    FD_ZERO(&selected); FD_SET(31, &selected);
    errno = 0;
    if (select(32, &selected, nullptr, nullptr, &instant) != -1 || errno != EBADF) return 32;
    const int duplicate = dup(1);
    if (duplicate < 0 || close(1) != 0) return 2;
    const pid_t posix_child = fork();
    if (posix_child == 0) {
        const char marker[] = "W1_LIBC_FORK\n";
        if (!isatty(duplicate) || write(duplicate, marker, sizeof(marker) - 1) != sizeof(marker) - 1)
            _exit(27);
        _exit(0);
    }
    int status = 0;
    if (posix_child < 0 || waitpid(posix_child, &status, 0) != posix_child ||
        !WIFEXITED(status) || WEXITSTATUS(status) != 0) return 5;
    char executable[] = "/missing", *arguments[] = {executable, nullptr};
    errno = 0;
    if (execv(executable, arguments) != -1 || errno != ENOENT) return 6;
    const char ready[] = "W1_APP_READY\n";
    for (u32 i = 0; i < sizeof(ready) - 1; ++i)
        if (write(duplicate, ready + i, 1) != 1) return 7;
    FD_ZERO(&selected); FD_SET(0, &selected);
    struct timeval wait_time{2, 0};
    if (select(1, &selected, nullptr, nullptr, &wait_time) != 1 || !FD_ISSET(0, &selected)) return 33;
    FD_ZERO(&selected); FD_SET(0, &selected); instant = {0, 0};
    if (select(1, &selected, nullptr, nullptr, &instant) != 1 || !FD_ISSET(0, &selected)) return 34;
    char input = 0;
    if (read(0, &input, 1) != 1 || input != 'A') return 8;
    const char select_ok[] = "W1_SELECT_OK\n";
    for (u32 i = 0; i < sizeof(select_ok) - 1; ++i)
        if (write(duplicate, select_ok + i, 1) != 1) return 35;
    if (!announce(duplicate, "W1_FLUSH_QUEUE_READY\n") || terminal_ready(2) != 1 ||
        tcflush(0, TCIFLUSH) != 0 || terminal_ready(0) != 0 ||
        !announce(duplicate, "W1_FLUSH_FRESH_READY\n") || terminal_ready(2) != 1 ||
        read(0, &input, 1) != 1 || input != 'F') return 36;
    if (!announce(duplicate, "W1_TCSA_QUEUE_READY\n") || terminal_ready(2) != 1) return 37;
    tty.c_cc[VMIN] = 0; tty.c_cc[VTIME] = 1;
    if (tcsetattr(0, TCSAFLUSH, &tty) != 0 || tcgetattr(0, &tty) != 0 ||
        tty.c_cc[VMIN] != 0 || tty.c_cc[VTIME] != 1 || terminal_ready(0) != 0 ||
        !announce(duplicate, "W1_TCSA_FRESH_READY\n") || terminal_ready(2) != 1 ||
        read(0, &input, 1) != 1 || input != 'N') return 38;
    tty.c_cc[VMIN] = 1; tty.c_cc[VTIME] = 0;
    if (tcsetattr(0, TCSANOW, &tty) != 0 || !announce(duplicate, "W1_FLUSH_OK\n")) return 39;
    const char message[] = "W1_APP_OK\n";
    for (u32 i = 0; i < sizeof(message) - 1; ++i)
        if (write(duplicate, message + i, 1) != 1) return 3;
    if (tcdrain(duplicate) != 0) return 17;
    if (close(duplicate) != 0) return 4;
    return 0;
}
