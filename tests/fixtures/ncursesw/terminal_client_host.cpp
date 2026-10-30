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
        if (last_request.operation == static_cast<u32>(terminal::operation::read_until)) {
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
    char buffer[300]{};
    if (terminal::read_until(client, buffer, sizeof(buffer), 10) != 1 || buffer[0] != 'Z' ||
        last_request.length != terminal::data_bytes || last_request.deadline_ns != 10) return 3;
    if (terminal::write_until(client, buffer, sizeof(buffer), 20) != 1 ||
        last_request.length != terminal::data_bytes || last_request.data[0] != 'Z') return 4;
    malformed = true;
    if (terminal::read_until(client, buffer, 1, 30) != process_error_state || closed != 2 ||
        client.send_handle != 0 || client.receive_handle != 0) return 5;
    return 0;
}
