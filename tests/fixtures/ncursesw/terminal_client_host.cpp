// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/terminal_client.hpp>
#include <xos/thread_abi.hpp>

using namespace xos;
namespace {
channel_info channels[2]{};
terminal::request last_request{};
bool malformed = false;
u32 closed = 0;
terminal::mode mode_value = terminal::default_mode;
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == sys_channel) {
        if (first == static_cast<u64>(channel_action::enumerate)) {
            if (second >= 2) return thread_error_not_found;
            *reinterpret_cast<channel_info*>(third) = channels[second]; return 0;
        }
        if (first == static_cast<u64>(channel_action::wait)) return 0;
        if (first == static_cast<u64>(channel_action::close)) { ++closed; return 0; }
    }
    if (number == 4 && third == sizeof(last_request)) {
        last_request = *reinterpret_cast<const terminal::request*>(second); return 0;
    }
    if (number == 5 && third == sizeof(terminal::response)) {
        auto& response = *reinterpret_cast<terminal::response*>(second);
        response = {}; response.version = terminal::version; response.size = sizeof(response);
        response.sequence = last_request.sequence; response.result = 1;
        if (last_request.operation == static_cast<u32>(terminal::operation::mode_get)) {
            response.result = 0; response.length = sizeof(mode_value);
            const auto* bytes = reinterpret_cast<const u8*>(&mode_value);
            for (u32 i = 0; i < sizeof(mode_value); ++i) response.data[i] = bytes[i];
        } else if (last_request.operation == static_cast<u32>(terminal::operation::mode_set)) {
            auto* bytes = reinterpret_cast<u8*>(&mode_value);
            for (u32 i = 0; i < sizeof(mode_value); ++i) bytes[i] = last_request.data[i];
            response.result = 0;
        } else if (last_request.operation == static_cast<u32>(terminal::operation::drain)) {
            response.result = 0;
        } else if (last_request.operation == static_cast<u32>(terminal::operation::flush_input)) {
            response.result = 0;
        } else if (last_request.operation == static_cast<u32>(terminal::operation::fork_attach)) {
            response.result = 0;
        } else if (last_request.operation == static_cast<u32>(terminal::operation::read_mode)) {
            response.result = 0;
        } else if (last_request.operation == static_cast<u32>(terminal::operation::read_until)) {
            response.length = malformed ? 2 : 1; response.data[0] = 'Z';
        }
        return sizeof(response);
    }
    return process_error_invalid;
}
}
int main() {
    channels[0] = {channel_version, sizeof(channel_info), 10, channel_send, 2, 1};
    channels[1] = {channel_version, sizeof(channel_info), 11, channel_receive, 2, 1};
    terminal::client client{};
    if (terminal::connect(client, 9, 2) != process_error_denied || client.send_handle != 0) return 1;
    struct startup_fixture { startup_info header; u8 padding[16]; startup_extension extension; } fixture{};
    static_assert(__builtin_offsetof(startup_fixture, extension) == startup_extension_offset);
    fixture.header.magic = startup_magic; fixture.header.version = 2; fixture.header.size = sizeof(startup_info);
    fixture.header.reserved = startup_extension_offset; fixture.extension.magic = startup_extension_magic;
    fixture.extension.flags = startup_flag_terminal; fixture.extension.reserved = 99;
    if (terminal::connect_startup(client, &fixture.header) != process_error_denied) return 2;
    fixture.extension.reserved = 10;
    if (terminal::connect_startup(client, &fixture.header) != 0) return 6;
    channel_fork_pair pair{channel_version, sizeof(channel_fork_pair), 8, 10, 11, 12, 13};
    if (terminal::register_fork(client, pair) != 0 ||
        last_request.operation != static_cast<u32>(terminal::operation::fork_attach) ||
        last_request.length != sizeof(terminal::session_channels)) return 12;
    const auto* fork_data = reinterpret_cast<const terminal::session_channels*>(last_request.data);
    if (fork_data->incoming != 12 || fork_data->outgoing != 13 || fork_data->peer_pid != 8) return 13;
    pair.source_send = 99;
    if (terminal::register_fork(client, pair) != process_error_invalid) return 14;
    terminal::mode selected{};
    if (terminal::get_mode(client, selected) != 0 || selected.vmin != 1 || selected.vtime != 0) return 7;
    selected.vmin = 0; selected.vtime = 1;
    if (terminal::set_mode(client, selected, terminal::mode_action::drain_flush_input) != 0 ||
        mode_value.vtime != 1 || last_request.deadline_ns != 2 ||
        terminal::drain(client) != 0 || terminal::flush_input(client) != 0) return 8;
    selected.lflag = 1;
    if (terminal::set_mode(client, selected) != thread_error_unsupported || mode_value.lflag != 0) return 9;
    char buffer[300]{};
    if (terminal::read_mode(client, buffer, 1) != 0) return 10;
    if (terminal::read_until(client, buffer, sizeof(buffer), 10) != 1 || buffer[0] != 'Z' ||
        last_request.length != terminal::data_bytes || last_request.deadline_ns != 10) return 3;
    if (terminal::write_until(client, buffer, sizeof(buffer), 20) != 1 ||
        last_request.length != terminal::data_bytes || last_request.data[0] != 'Z') return 4;
    malformed = true;
    if (terminal::read_until(client, buffer, 1, 30) != process_error_state || closed != 2 ||
        client.send_handle != 0 || client.receive_handle != 0) return 5;
    struct exec_fixture {
        startup_info header; u8 padding[16]; startup_extension extension;
        startup_exec_extension exec; startup_terminal_exec_extension terminal_exec;
    } replacement{};
    static_assert(__builtin_offsetof(exec_fixture, terminal_exec) == startup_terminal_exec_offset);
    replacement.header.magic = startup_magic; replacement.header.version = 3;
    replacement.header.size = sizeof(startup_info); replacement.header.reserved = startup_extension_offset;
    replacement.extension.magic = startup_extension_magic;
    replacement.extension.flags = startup_flag_terminal; replacement.extension.reserved = 10;
    replacement.terminal_exec = {startup_terminal_exec_magic, 42};
    malformed = false;
    if (terminal::connect_startup(client, &replacement.header) != 0 || client.next_sequence != 42 ||
        terminal::get_mode(client, selected) != 0 || last_request.sequence != 42) return 11;
    terminal::close(client);
    return 0;
}
