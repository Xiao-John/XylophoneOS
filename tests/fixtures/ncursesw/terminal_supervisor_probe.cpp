// SPDX-License-Identifier: Apache-2.0
// Dedicated test supervisor, never selected by a normal build.
#include <xos/sdk.hpp>
#include <xos/file_ui.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
terminal::control session;

bool transmit(const char* text) {
    for (u32 offset = 0; text[offset] != 0;) {
        terminal::request request{}; terminal::response response{};
        request.operation = static_cast<u32>(terminal::operation::write);
        request.length = 1; request.data[0] = static_cast<u8>(text[offset]);
        bool written = false;
        for (u32 retry = 0; retry < 2000; ++retry) {
            if (terminal::exchange(session, request, response) != 0) return false;
            if (response.result == 1) { written = true; break; }
            if (response.result != process_error_would_block) return false;
            sdk::yield();
        }
        if (!written) return false;
        ++offset;
    }
    return true;
}

bool stop() {
    terminal::request request{}; terminal::response response{};
    request.operation = static_cast<u32>(terminal::operation::stop);
    if (terminal::exchange(session, request, response) != 0 || response.result != 0) return false;
    process_status status{};
    const i64 result = sdk::wait(session.child, status);
    terminal::close(session);
    return result == 0 && status.outcome == process_outcome::exited && status.code == 0;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    for (u64 demo = 1; demo <= 4; ++demo) (void)sdk::syscall(10, demo);
    ui::init();
    sdk::print("W1_BOOT_READY\n");
    char trigger = 0;
    while (sdk::read(0, &trigger, 1) != 1) sdk::yield();
    if (trigger != '!') return 1;
    if (terminal::start(session, "/bin/terminal.elf") <= 0) return 2;
    if (!transmit("W1_READ_READY\n")) return 3;
    terminal::request request{}; terminal::response response{};
    request.operation = static_cast<u32>(terminal::operation::read_until);
    request.length = 1; request.deadline_ns = thread_deadline_infinite;
    if (terminal::exchange(session, request, response) != 0 || response.result != 1 ||
        response.length != 1 || response.data[0] != 'R') return 4;
    if (!transmit("W1_READ_OK\n")) return 5;
    terminal::request pending{}, cancel{};
    pending.operation = static_cast<u32>(terminal::operation::read_until);
    pending.length = 1; pending.deadline_ns = thread_deadline_infinite;
    cancel.operation = static_cast<u32>(terminal::operation::cancel);
    if (terminal::submit(session, pending) != 0 || terminal::submit(session, cancel) != 0 ||
        terminal::receive(session, response) != 0 || response.sequence != pending.sequence ||
        response.result != terminal::interrupted || terminal::receive(session, response) != 0 ||
        response.sequence != cancel.sequence || response.result != 0) return 6;
    if (!transmit("W1_CANCEL_OK\n")) return 7;
    if (!stop()) return 8;
    if (sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1) != 2 ||
        sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1) != 0) return 9;
    if (terminal::start(session, "/bin/terminal.elf") <= 0) return 10;
    if (!transmit("W1_REAUTHORIZE_OK\n")) return 11;
    return stop() ? 0 : 12;
}
