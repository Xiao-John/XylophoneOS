// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/interactium_abi.hpp>

namespace {
using namespace xos;
using namespace xos::interactium;

bool exchange(const ipc_channel& channel, const wire_header& request,
              const void* payload, u32 payload_size, u8* response, u32& response_size) {
    alignas(8) u8 message[sizeof(wire_header) + sizeof(create_window_payload)]{};
    wire_header header = request;
    header.size = sizeof(wire_header) + payload_size;
    header.payload_length = payload_size;
    for (u32 i = 0; i < sizeof(header); ++i) message[i] = reinterpret_cast<const u8*>(&header)[i];
    const auto* source = static_cast<const u8*>(payload);
    for (u32 i = 0; i < payload_size; ++i) message[sizeof(header) + i] = source[i];
    if (xos::sdk::ipc_send(channel.send, message, header.size) != 0 ||
        xos::sdk::ipc_wait(channel.receive, ipc_wait_mode::receive) != 0) return false;
    const i64 received = xos::sdk::ipc_recv(channel.receive, response,
                                             sizeof(wire_header) + sizeof(hello_reply_payload));
    if (received < static_cast<i64>(sizeof(wire_header))) return false;
    response_size = static_cast<u32>(received);
    return true;
}

bool read_header(const u8* response, u32 size, wire_header& header) {
    if (size < sizeof(header)) return false;
    auto* destination = reinterpret_cast<u8*>(&header);
    for (u32 i = 0; i < sizeof(header); ++i) destination[i] = response[i];
    return header.version == protocol_version && header.size == size &&
           header.payload_length == size - sizeof(header);
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    using namespace xos::interactium;
    ipc_channel channel{};
    if (sdk::ipc_name_connect("interactium", channel) != 0) return 20;

    u8 response[sizeof(wire_header) + sizeof(hello_reply_payload)]{};
    u32 response_size = 0;
    const hello_payload hello{protocol_version, 0, 800, 600};
    wire_header request{protocol_version, 0, message_type::hello, 0, 1, 0, 0, 0, 0};
    if (!exchange(channel, request, &hello, sizeof(hello), response, response_size)) return 21;
    wire_header reply{};
    if (!read_header(response, response_size, reply) || reply.type != message_type::hello_reply ||
        reply.session == 0 || reply.payload_length != sizeof(hello_reply_payload)) return 22;
    const u64 session = reply.session;

    const create_window_payload create{40, 40, 240, 160, window_role::normal, 0, 0};
    request = {protocol_version, 0, message_type::create_window, 0, 2, session, 0, 0, 0};
    if (!exchange(channel, request, &create, sizeof(create), response, response_size) ||
        !read_header(response, response_size, reply) || reply.type != message_type::ack ||
        reply.object == 0 || reply.payload_length != sizeof(status_payload)) return 23;
    status_payload status{};
    for (u32 i = 0; i < sizeof(status); ++i) reinterpret_cast<u8*>(&status)[i] = response[sizeof(wire_header) + i];
    if (status.result != 0) return 24;

    request = {protocol_version, 0, message_type::disconnect, 0, 3, session, 0, 0, 0};
    if (!exchange(channel, request, nullptr, 0, response, response_size) ||
        !read_header(response, response_size, reply) || reply.type != message_type::ack) return 25;
    if (sdk::ipc_channel_close(channel.send) != 0) return 26;
    sdk::print("INTERACTIUM_CLIENT_PASS\n");
    return 0;
}
