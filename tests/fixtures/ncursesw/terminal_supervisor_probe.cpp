// SPDX-License-Identifier: Apache-2.0
// Dedicated test supervisor, never selected by a normal build.
#include <xos/sdk.hpp>
#include <xos/file_ui.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>
#include <xos/channel_io.hpp>

namespace {
using namespace xos;
terminal::control session;
terminal::application app;

i64 prepare_app(u64 child, void*) { return terminal::attach(session, app, child); }
struct pio_context { bool revoke; u32 ready, go; };
i64 prepare_pio(u64 child, void* context) {
    auto& state = *static_cast<pio_context*>(context);
    if (state.revoke) {
        channel_create request{channel_version, sizeof(channel_create), child, sdk::pid(), 1, 0};
        i64 result = sdk::channel_open(request);
        if (result <= 0) return result < 0 ? result : process_error_state;
        state.ready = static_cast<u32>(result);
        request.sender_pid = sdk::pid(); request.receiver_pid = child;
        result = sdk::channel_open(request);
        if (result <= 0) { (void)sdk::channel_close(state.ready); return result < 0 ? result : process_error_state; }
        state.go = static_cast<u32>(result);
    }
    return sdk::pio_grant(pio_grant_action::grant, child, pio_resource_com1);
}

bool pio_boundary(const char* mode, bool fault) {
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.grant_spawn = true;
    pio_context state{sdk::equal(mode, "revoke") || sdk::equal(mode, "revoke_thread"), 0, 0};
    options.prepare_child = prepare_pio; options.prepare_context = &state;
    const char* argv[] = {"/bin/pio_auth.elf", mode};
    const i64 child = sdk::spawn_file_options(argv[0], 2, argv, options);
    if (child <= 0) return false;
    if (state.revoke) {
        char byte = 0;
        if (sdk::channel_receive_wait(state.ready, &byte, 1, thread_deadline_infinite) != 1 || byte != 'r' ||
            sdk::pio_grant(pio_grant_action::revoke, static_cast<u64>(child), pio_resource_com1) != 0 ||
            sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1) != 2) return false;
        byte = 'g';
        if (sdk::channel_send_wait(state.go, &byte, 1, thread_deadline_infinite) != 0) return false;
    }
    process_status status{};
    if (sdk::wait(static_cast<u64>(child), status) != 0) return false;
    if (fault ? status.outcome != process_outcome::faulted || status.vector != 13
              : status.outcome != process_outcome::exited || status.code != 0) return false;
    return sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1) == 2 &&
           sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1) == 0;
}

bool transmit(const char* text) {
    for (u32 offset = 0; text[offset] != 0;) {
        const i64 written = terminal::write_until(session, text + offset, 1, thread_deadline_infinite);
        if (written != 1) return false;
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
    if (!pio_boundary("inside", false) || !pio_boundary("below", true) ||
        !pio_boundary("above", true) || !pio_boundary("cross", true) ||
        !pio_boundary("fork", false) || !pio_boundary("badexec", false) ||
        !pio_boundary("exec", true) || !pio_boundary("revoke", true) ||
        !pio_boundary("revoke_thread", true) || !pio_boundary("irq_empty", false) ||
        !pio_boundary("irq_delivery", false) || !pio_boundary("irq_wait_close", false)) return 17;
    if (terminal::start(session, "/bin/terminal.elf") <= 0) return 2;
    if (!transmit("W1_PIO_BOUNDS_OK\n")) return 18;
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
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    // Dedicated probe grants bounded process creation for the fork-session test.
    options.grant_spawn = true;
    options.prepare_child = prepare_app; options.terminal_send_handle = &app.incoming;
    const char* argv[] = {"/bin/tty_app.elf"};
    const i64 child = sdk::spawn_file_options(argv[0], 1, argv, options);
    if (child <= 0) { terminal::close(app); return 13; }
    process_status app_status{};
    if (sdk::wait(static_cast<u64>(child), app_status) != 0 ||
        app_status.outcome != process_outcome::exited || app_status.code != 0) return 14;
    if (terminal::detach(session, app) != 0) return 15;
    if (!transmit("W1_APP_REAPED\n")) return 16;
    if (!stop()) return 8;
    if (sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1) != 2 ||
        sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1) != 0) return 9;
    if (terminal::start(session, "/bin/terminal.elf") <= 0) return 10;
    if (!transmit("W1_REAUTHORIZE_OK\n")) return 11;
    return stop() ? 0 : 12;
}
