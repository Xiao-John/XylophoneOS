// SPDX-License-Identifier: Apache-2.0
// Dedicated test supervisor, never selected by a normal build.
#include <xos/sdk.hpp>
#include <xos/file_ui.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
terminal::control session;
terminal::application app;

i64 prepare_app(u64 child, void*) { return terminal::attach(session, app, child); }

bool transmit(const char* text) {
    for (u32 offset = 0; text[offset] != 0; ++offset)
        if (terminal::write_until(session, text + offset, 1, thread_deadline_infinite) != 1) return false;
    return true;
}

bool run(const char* path) {
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.prepare_child = prepare_app; options.terminal_send_handle = &app.incoming;
    const char* environment[] = {"TERM=xterm", "TERMINFO=/usr/local/share/terminfo", "LINES=24", "COLUMNS=80"};
    options.environment = environment; options.environment_count = 4;
    const char* arguments[] = {path};
    const i64 child = sdk::spawn_file_options(path, 1, arguments, options);
    if (child <= 0) { terminal::close(app); return false; }
    process_status status{};
    const i64 waited = sdk::wait(static_cast<u64>(child), status);
    const i64 detached = terminal::detach(session, app);
    if (waited == 0 && status.outcome == process_outcome::exited && status.code >= 0 && status.code <= 9) {
        char detail[] = "W2_CHILD_EXIT_0\n";
        detail[14] = static_cast<char>('0' + status.code);
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
    if (terminal::start(session, "/bin/terminal.elf") <= 0) return 2;
    if (!transmit("W2_SERVICE_READY\n")) return 3;
    if (!run("/bin/wide.elf")) { (void)transmit("W2_WIDE_FAILED\n"); return 4; }
    if (!transmit("W2_WIDE_OK\n")) return 5;
    if (!run("/bin/reentry.elf")) { (void)transmit("W2_REENTRY_FAILED\n"); return 6; }
    if (!transmit("W2_REENTRY_OK\n")) return 7;
    terminal::request request{}; terminal::response response{};
    request.operation = static_cast<u32>(terminal::operation::stop);
    if (terminal::exchange(session, request, response) != 0 || response.result != 0) return 8;
    process_status status{};
    const i64 waited = sdk::wait(session.child, status);
    terminal::close(session);
    return waited == 0 && status.outcome == process_outcome::exited && status.code == 0 ? 0 : 9;
}
