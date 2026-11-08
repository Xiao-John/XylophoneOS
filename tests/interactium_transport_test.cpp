// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstring>
#include "../src/user/interactium/service_loop.hpp"

using namespace xos;
using namespace xos::interactium;

class fake_transport final : public session_transport {
    u64 owner_;
    u8 incoming_[4][max_wire_message]{};
    u32 incoming_size_[4]{};
    u32 incoming_count_ = 0;
    u8 outgoing_[4][max_wire_message]{};
    u32 outgoing_size_[4]{};
    u32 outgoing_count_ = 0;
    bool closed_ = false;

public:
    explicit fake_transport(u64 owner) : owner_(owner) {}
    u64 authenticated_owner() const override { return owner_; }
    bool closed() const override { return closed_; }
    void close() { closed_ = true; }
    void push(const u8* message, u32 size) {
        assert(incoming_count_ < 4 && size <= max_wire_message);
        std::memcpy(incoming_[incoming_count_], message, size);
        incoming_size_[incoming_count_++] = size;
    }
    i32 receive(u8* buffer, u32 capacity, u32& size) override {
        if (closed_) return transport_closed;
        if (incoming_count_ == 0) return transport_again;
        assert(incoming_size_[0] <= capacity);
        size = incoming_size_[0];
        std::memcpy(buffer, incoming_[0], size);
        for (u32 i = 1; i < incoming_count_; ++i) {
            std::memcpy(incoming_[i - 1], incoming_[i], incoming_size_[i]);
            incoming_size_[i - 1] = incoming_size_[i];
        }
        --incoming_count_;
        return static_cast<i32>(size);
    }
    i32 send(const u8* buffer, u32 size) override {
        assert(outgoing_count_ < 4 && size <= max_wire_message);
        std::memcpy(outgoing_[outgoing_count_], buffer, size);
        outgoing_size_[outgoing_count_++] = size;
        return static_cast<i32>(size);
    }
    u32 replies() const { return outgoing_count_; }
    const u8* reply(u32 index) const { return outgoing_[index]; }
};

static void message(u8* buffer, u32& size, u64 sequence, u64 session,
                    message_type type, u64 object, const void* payload = nullptr,
                    u32 payload_size = 0) {
    const wire_header header{protocol_version, static_cast<u32>(sizeof(wire_header) + payload_size),
                             type, 0, sequence, session, object, payload_size, 0};
    std::memcpy(buffer, &header, sizeof(header));
    if (payload_size != 0) std::memcpy(buffer + sizeof(header), payload, payload_size);
    size = header.size;
}

static i64 status(const u8* buffer) {
    status_payload payload{};
    std::memcpy(&payload, buffer + sizeof(wire_header), sizeof(payload));
    return payload.result;
}

int main() {
    service model;
    fake_transport first(501), second(502);
    service_loop first_loop(model, first), second_loop(model, second);
    alignas(8) u8 request[max_wire_message]{};
    u32 request_size = 0;
    assert(first_loop.step() == loop_result::again);
    const hello_payload hello{protocol_version, 0, 800, 600};
    message(request, request_size, 1, 0, message_type::hello, 0, &hello, sizeof(hello));
    first.push(request, request_size);
    assert(first_loop.step() == loop_result::progressed && first.replies() == 1);
    wire_header reply_header{};
    std::memcpy(&reply_header, first.reply(0), sizeof(reply_header));
    assert(reply_header.type == message_type::hello_reply && first_loop.connected());
    const u64 first_session = reply_header.session;

    const create_window_payload create{0, 0, 240, 160, window_role::normal, 0, 0};
    message(request, request_size, 2, first_session, message_type::create_window, 0,
            &create, sizeof(create));
    first.push(request, request_size);
    assert(first_loop.step() == loop_result::progressed && first.replies() == 2);
    std::memcpy(&reply_header, first.reply(1), sizeof(reply_header));
    assert(status(first.reply(1)) == 0 && reply_header.object != 0);

    message(request, request_size, 1, 0, message_type::hello, 0, &hello, sizeof(hello));
    second.push(request, request_size);
    assert(second_loop.step() == loop_result::progressed && second.replies() == 1);
    std::memcpy(&reply_header, second.reply(0), sizeof(reply_header));

    message(request, request_size, 3, first_session, message_type::disconnect, 0);
    first.push(request, request_size);
    assert(first_loop.step() == loop_result::session_closed);
    assert(status(first.reply(2)) == 0 && !first_loop.connected());
    assert(second_loop.connected());

    fake_transport dropped(501);
    service_loop dropped_loop(model, dropped);
    message(request, request_size, 1, 0, message_type::hello, 0, &hello, sizeof(hello));
    dropped.push(request, request_size);
    assert(dropped_loop.step() == loop_result::progressed && dropped_loop.connected());
    wire_header dropped_reply{};
    std::memcpy(&dropped_reply, dropped.reply(0), sizeof(dropped_reply));
    const create_window_payload dropped_create{20, 20, 200, 120, window_role::normal, 0, 0};
    message(request, request_size, 2, dropped_reply.session, message_type::create_window, 0,
            &dropped_create, sizeof(dropped_create));
    dropped.push(request, request_size);
    assert(dropped_loop.step() == loop_result::progressed);
    wire_header dropped_window_reply{};
    std::memcpy(&dropped_window_reply, dropped.reply(1), sizeof(dropped_window_reply));
    assert(model.get_window(window_id{dropped_window_reply.object}) != nullptr);
    dropped.close();
    assert(dropped_loop.step() == loop_result::session_closed && !dropped_loop.connected());
    assert(model.get_window(window_id{dropped_window_reply.object}) == nullptr);

    fake_transport reconnect(501);
    service_loop reconnect_loop(model, reconnect);
    message(request, request_size, 1, 0, message_type::hello, 0, &hello, sizeof(hello));
    reconnect.push(request, request_size);
    assert(reconnect_loop.step() == loop_result::progressed && reconnect_loop.connected());
    return 0;
}
