// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/terminal_control.hpp>

using namespace xos;
namespace {
u32 next_handle = 10, closed = 0;
bool fail_grant = false, fail_reply = false;
u32 send_attempts = 0, receive_attempts = 0;
terminal::request sent{};
u64 queued_sequences[8]{};
u32 queued_count = 0, received_count = 0;
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == 6) return 1;
    if (number == sys_channel) {
        if (first == static_cast<u64>(channel_action::create)) return next_handle++;
        if (first == static_cast<u64>(channel_action::close)) { ++closed; return 0; }
        if (first == static_cast<u64>(channel_action::wait)) {
            return fail_reply && second == 11 ? process_error_state : 0;
        }
    }
    if (number == sys_pio_grant) return fail_grant ? process_error_denied : 0;
    if (number == 4 && third == sizeof(sent)) {
        if (++send_attempts == 1) return -4;
        sent = *reinterpret_cast<const terminal::request*>(second);
        if (queued_count >= 8) return process_error_resources;
        queued_sequences[queued_count++] = sent.sequence; return 0;
    }
    if (number == 5 && third == sizeof(terminal::response)) {
        if (++receive_attempts == 1) return -3;
        auto& reply = *reinterpret_cast<terminal::response*>(second);
        reply = {}; reply.version = terminal::version; reply.size = sizeof(reply);
        reply.sequence = queued_sequences[received_count++]; reply.result = 0;
        return sizeof(reply);
    }
    return process_error_invalid;
}
i64 spawn_file_options(const char*, u32, const char* const*, const spawn_options& options) {
    const i64 result = options.prepare_child(2, options.prepare_context);
    return result == 0 ? 2 : result;
}
}
int main() {
    terminal::control session{};
    fail_grant = true;
    if (terminal::start(session, "/terminal") != process_error_denied || closed != 2 || session.child != 0)
        return 1;
    fail_grant = false; next_handle = 10;
    if (terminal::start(session, "/terminal") != 2) return 2;
    terminal::request request{}; terminal::response reply{};
    if (terminal::exchange(session, request, reply) != 0 || request.sequence != 1 || reply.sequence != 1 ||
        send_attempts != 2 || receive_attempts != 2)
        return 3;
    terminal::request first{}, second{}, third{};
    if (terminal::submit(session, first) != 0 || terminal::submit(session, second) != 0 ||
        terminal::submit(session, third) != process_error_busy ||
        terminal::exchange(session, third, reply) != process_error_busy ||
        terminal::receive(session, reply) != 0 || reply.sequence != first.sequence ||
        terminal::receive(session, reply) != 0 || reply.sequence != second.sequence) return 7;
    terminal::application app{};
    if (terminal::attach(session, app, 3) != 0 || app.peer != 3 || app.incoming == 0 || app.outgoing == 0 ||
        terminal::detach(session, app) != 0 || app.peer != 0 || closed != 4) return 8;
    fail_reply = true;
    if (terminal::exchange(session, request, reply) != process_error_state || closed != 6 ||
        session.child != 2 || session.send_handle != 0 || session.receive_handle != 0) return 4;
    if (terminal::exchange(session, request, reply) != process_error_state) return 5;
    terminal::close(session);
    return session.child == 0 ? 0 : 6;
}
