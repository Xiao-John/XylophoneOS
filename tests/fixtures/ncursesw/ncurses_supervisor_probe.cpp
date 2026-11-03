// SPDX-License-Identifier: Apache-2.0
// Dedicated test supervisor, never selected by a normal build.
#include <xos/sdk.hpp>
#include <xos/file_ui.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>
#include "../../../src/user/services/shell_terminal.hpp"

namespace {
using namespace xos;
bool transmit(const char* text) {
    for (u32 offset = 0; text[offset] != 0; ++offset)
        if (sdk::write(1, text + offset, 1) != 1) return false;
    return true;
}

bool run(const char* path) {
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.prepare_child = user::shell_terminal::prepare_application;
    options.terminal_send_handle = user::shell_terminal::application_send_handle();
    const char* environment[] = {"TERM=xterm", "TERMINFO=/usr/local/share/terminfo", "LINES=24", "COLUMNS=80"};
    options.environment = environment; options.environment_count = 4;
    const char* arguments[] = {path};
    const i64 child = sdk::spawn_file_options(path, 1, arguments, options);
    if (child <= 0) {
        if (*options.terminal_send_handle != 0) (void)user::shell_terminal::finish_application();
        return false;
    }
    process_status status{};
    const i64 waited = sdk::wait(static_cast<u64>(child), status);
    const i64 detached = user::shell_terminal::finish_application();
    if (waited == 0 && status.outcome == process_outcome::exited && status.code >= 0 && status.code <= 99) {
        char detail[] = "W2_CHILD_EXIT_00\n";
        detail[14] = static_cast<char>('0' + status.code / 10);
        detail[15] = static_cast<char>('0' + status.code % 10);
        (void)transmit(detail);
    }
    return waited == 0 && detached == 0 && status.outcome == process_outcome::exited && status.code == 0;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    for (u64 demo = 1; demo <= 4; ++demo) (void)sdk::syscall(10, demo);
    ui::init();
    sdk::print("W2_BOOT_READY\n");
    char trigger = 0;
    while (sdk::read(0, &trigger, 1) != 1) sdk::yield();
    if (trigger != '!') return 1;
    const i64 terminal_child = user::shell_terminal::start("/bin/terminal.elf");
    if (terminal_child <= 0) return 2;
    if (!transmit("W2_SERVICE_READY\n")) return 3;
    if (!run("/bin/wide.elf")) { (void)transmit("W2_WIDE_FAILED\n"); return 4; }
    if (!transmit("W2_WIDE_OK\n")) return 5;
    if (!run("/bin/reentry.elf")) { (void)transmit("W2_REENTRY_FAILED\n"); return 6; }
    if (!transmit("W2_REENTRY_OK\n")) return 7;
    if (!run("/bin/locale.elf")) { (void)transmit("W2_LOCALE_FAILED\n"); return 9; }
    if (!transmit("W2_LOCALE_OK\n")) return 10;
    if (sdk::syscall(10, static_cast<u64>(terminal_child)) != 0) return 11;
    if (sdk::write(1, "X", 1) >= 0) return 12;
    const i64 restarted = user::shell_terminal::recover("/bin/terminal.elf");
    if (restarted <= 0) return 13;
    if (!transmit("W2_RECOVER_OK\n")) return 14;
    if (!run("/bin/locale.elf")) { (void)transmit("W2_RECOVER_APP_FAILED\n"); return 15; }
    if (!transmit("W2_RECOVER_APP_OK\n")) return 16;
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.prepare_child = user::shell_terminal::prepare_application;
    options.terminal_send_handle = user::shell_terminal::application_send_handle();
    options.grant_spawn = true;
    const char* args[] = {"/bin/failure.elf"};
    const i64 fault_app = sdk::spawn_file_options(args[0], 1, args, options);
    if (fault_app <= 0) return 17;
    const i64 now = sdk::syscall(sys_clock_monotonic);
    if (now < 0 || sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 500000000) != 0) return 18;
    if (sdk::syscall(10, static_cast<u64>(restarted)) != 0) return 19;
    process_status fault_status{};
    if (sdk::wait(static_cast<u64>(fault_app), fault_status) != 0 ||
        fault_status.outcome != process_outcome::exited || fault_status.code != 0) return 20;
    if (user::shell_terminal::finish_application() == 0) return 21;
    if (user::shell_terminal::recover("/bin/terminal.elf") <= 0) return 22;
    if (!transmit("W2_FAULT_APP_RECOVER_OK\n")) return 23;
    return user::shell_terminal::stop() == 0 ? 0 : 8;
}
